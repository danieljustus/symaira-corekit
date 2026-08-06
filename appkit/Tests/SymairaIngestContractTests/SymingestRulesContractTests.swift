import XCTest
import Foundation
@testable import SymairaIngestContract
import SymairaToolKit

final class SymingestRulesContractTests: XCTestCase {
    func testVersionedClassificationAndDryRunEnvelopesDecode() throws {
        let list = try SymingestRulesContract.decodeList(from: Data("""
        {"schema_version":1,"rules":[{"id":7,"pattern":"invoice","kind":"category","value":"Finance","created_at":"2026-07-12T10:00:00Z"}]}
        """.utf8))
        XCTAssertEqual(list.rules.first?.id, 7)

        let dryRun = try SymingestRulesContract.decodeDryRun(from: Data("""
        {"schema_version":1,"operation":"dry_run","proposed_rule":{"pattern":"invoice","kind":"tag","value":"Review"},"vault_path":"/vault","total_documents":2,"matched_documents":1,"skipped_documents":0,"matches":[{"document_id":7,"note_path":"/vault/invoice.md","title":"Invoice","matched_rule_ids":[3]}],"skipped":[]}
        """.utf8))
        XCTAssertEqual(dryRun.matchedDocuments, 1)
        XCTAssertEqual(dryRun.matches.first?.matchedRuleIDs, [3])
    }

    func testMailEnvelopeDecodesAndMasksRemainData() throws {
        let response = try SymingestRulesContract.decodeMail(from: Data("""
        {"schema_version":1,"operation":"list","config_path":"/tmp/config.toml","accounts":[{"id":"daniel@imap.example.com:993/INBOX","host":"imap.example.com","port":993,"username":"daniel","password_secret":"<redacted>","password_secret_kind":"plaintext","password_secret_configured":true,"folder":"INBOX","from":[],"subject":[],"has_attachment":false,"action":"mark_seen","move_to":"","archive_mail":false}],"reload_required":false}
        """.utf8))
        XCTAssertEqual(response.accounts.first?.passwordSecret, "<redacted>")
        XCTAssertFalse(response.reloadRequired)
    }

    func testUnsupportedSchemaFailsClearly() {
        XCTAssertThrowsError(try SymingestRulesContract.decodeList(from: Data("{\"schema_version\":2,\"rules\":[]}".utf8))) { error in
            XCTAssertEqual(error as? SymingestRulesError, .unsupportedSchema(2))
        }
    }

    func testSchemaVersionCheckDecode() throws {
        struct Dummy: Decodable, Sendable {}
        XCTAssertThrowsError(try SymingestRulesContract.decodeWithSchemaCheck(Data("{\"schema_version\":2}".utf8)) as Dummy) { error in
            XCTAssertEqual(error as? SymingestRulesError, .unsupportedSchema(2))
        }
    }

    func testMissingBinaryFailsClearly() async {
        let locator = BinaryLocator(searchPATH: "", extraDirectories: [])
        let client = SymingestRulesClient(locator: locator)
        do {
            _ = try await client.listRules()
            XCTFail("expected missing binary error")
        } catch {
            XCTAssertEqual(error as? SymingestRulesError, .missingBinary)
        }
    }

    func testMailAccountStableIDAndPasswordSecretKind() {
        let account = MailAccount(id: nil, host: "imap.example.com", port: 993, username: "daniel", passwordSecret: "symvault://imap/daniel")
        XCTAssertEqual(account.stableID, "daniel@imap.example.com:993/INBOX")
        XCTAssertEqual(account.passwordSecretKind, "symvault")

        let plain = MailAccount(host: "imap.example.com", username: "daniel", passwordSecret: "hunter2")
        XCTAssertEqual(plain.passwordSecretKind, "plaintext")

        let redacted = MailAccount(host: "imap.example.com", username: "daniel", passwordSecret: "<redacted>")
        XCTAssertEqual(redacted.passwordSecretKind, "redacted")
    }

    func testMailAccountEncodesSnakeCaseProtocolKeys() throws {
        let account = MailAccount(
            host: "imap.example.com",
            username: "daniel",
            passwordSecret: "symvault://imap/daniel",
            hasAttachment: true,
            moveTo: "Archive",
            archiveMail: true
        )
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder().encode(account)) as? [String: Any]
        )
        XCTAssertEqual(object["password_secret"] as? String, "symvault://imap/daniel")
        XCTAssertEqual(object["has_attachment"] as? Bool, true)
        XCTAssertEqual(object["move_to"] as? String, "Archive")
        XCTAssertEqual(object["archive_mail"] as? Bool, true)
        XCTAssertNil(object["passwordSecret"])
    }

    func testRegistryIngestToolReachableWithoutTrapping() throws {
        let tool = try SymairaToolRegistry.ingestTool
        XCTAssertEqual(tool.id, "symingest")
        XCTAssertEqual(tool.binaryName, "symingest")
    }

    // MARK: - Decode error mapping (table-driven)

    private func assertDecodeFailure(
        _ json: String,
        expected: SymingestRulesError,
        decode: (Data) throws -> Void,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertThrowsError(try decode(Data(json.utf8)), file: file, line: line) { error in
            XCTAssertEqual(error as? SymingestRulesError, expected, file: file, line: line)
        }
    }

    func testDecodeListErrorMappingIsExplicit() {
        let cases: [(String, SymingestRulesError)] = [
            ("", .invalidResponse), // empty data
            ("not json", .invalidResponse), // not parseable
            ("[]", .invalidResponse), // not a JSON object
            (#"{"rules":[]}"#, .invalidResponse), // schema_version missing
            (#"{"schema_version":"1","rules":[]}"#, .invalidResponse), // wrong type
            (#"{"schema_version":1}"#, .invalidResponse), // required key missing
            (#"{"schema_version":1,"rules":"nope"}"#, .invalidResponse), // wrong value type
            (#"{"schema_version":2,"rules":[]}"#, .unsupportedSchema(2)),
            (#"{"schema_version":9,"rules":[]}"#, .unsupportedSchema(9)),
        ]
        for (json, expected) in cases {
            assertDecodeFailure(json, expected: expected) { try SymingestRulesContract.decodeList(from: $0) }
        }
    }

    func testDecodeRuleErrorMappingIsExplicit() {
        let cases: [(String, SymingestRulesError)] = [
            ("", .invalidResponse),
            ("not json", .invalidResponse),
            (#"{"schema_version":1}"#, .invalidResponse), // rule missing
            (#"{"schema_version":1,"rule":{}}"#, .invalidResponse), // rule fields missing
            (#"{"schema_version":1,"rule":{"id":"x","pattern":"p","kind":"k","value":"v"}}"#, .invalidResponse),
            (#"{"schema_version":3,"rule":{}}"#, .unsupportedSchema(3)),
        ]
        for (json, expected) in cases {
            assertDecodeFailure(json, expected: expected) { try SymingestRulesContract.decodeRule(from: $0) }
        }
    }

    func testDecodeTestErrorMappingIsExplicit() {
        let cases: [(String, SymingestRulesError)] = [
            ("", .invalidResponse),
            (#"{"schema_version":1}"#, .invalidResponse), // matches missing
            (#"{"schema_version":1,"matches":{}}"#, .invalidResponse), // not an array
            (#"{"schema_version":2,"matches":[]}"#, .unsupportedSchema(2)),
        ]
        for (json, expected) in cases {
            assertDecodeFailure(json, expected: expected) { try SymingestRulesContract.decodeTest(from: $0) }
        }
    }

    func testDecodeDeleteErrorMappingIsExplicit() {
        let cases: [(String, SymingestRulesError)] = [
            ("", .invalidResponse),
            (#"{"schema_version":1,"id":7}"#, .invalidResponse), // deleted missing
            (#"{"schema_version":1,"deleted":true}"#, .invalidResponse), // id missing
            (#"{"schema_version":1,"id":7,"deleted":"yes"}"#, .invalidResponse),
            (#"{"schema_version":4,"id":7,"deleted":true}"#, .unsupportedSchema(4)),
        ]
        for (json, expected) in cases {
            assertDecodeFailure(json, expected: expected) { try SymingestRulesContract.decodeDelete(from: $0) }
        }
    }

    func testDecodeDryRunErrorMappingIsExplicit() {
        let cases: [(String, SymingestRulesError)] = [
            ("", .invalidResponse),
            (#"{"schema_version":1}"#, .invalidResponse), // nested fields missing
            (#"{"schema_version":1,"operation":"dry_run","proposed_rule":{},"vault_path":"/v","total_documents":1,"matched_documents":1,"skipped_documents":0,"matches":[],"skipped":[]}"#, .invalidResponse),
            (#"{"schema_version":1,"operation":"dry_run","proposed_rule":{"pattern":"p","kind":"k","value":"v"},"vault_path":"/v","total_documents":"1","matched_documents":1,"skipped_documents":0,"matches":[],"skipped":[]}"#, .invalidResponse),
            (#"{"schema_version":5,"operation":"dry_run","proposed_rule":{"pattern":"p","kind":"k","value":"v"},"vault_path":"/v","total_documents":1,"matched_documents":1,"skipped_documents":0,"matches":[],"skipped":[]}"#, .unsupportedSchema(5)),
        ]
        for (json, expected) in cases {
            assertDecodeFailure(json, expected: expected) { try SymingestRulesContract.decodeDryRun(from: $0) }
        }
    }

    func testDecodeMailErrorMappingIsExplicit() {
        let cases: [(String, SymingestRulesError)] = [
            ("", .invalidResponse),
            (#"{"schema_version":1,"operation":"list"}"#, .invalidResponse), // config_path missing
            (#"{"schema_version":1,"operation":"list","config_path":"/c","accounts":[{}],"reload_required":true}"#, .invalidResponse), // account with missing host
            (#"{"schema_version":1,"operation":"list","config_path":"/c","accounts":[{"host":"h"}],"reload_required":"no"}"#, .invalidResponse),
            (#"{"schema_version":6,"operation":"list","config_path":"/c","accounts":[],"reload_required":false}"#, .unsupportedSchema(6)),
        ]
        for (json, expected) in cases {
            assertDecodeFailure(json, expected: expected) { try SymingestRulesContract.decodeMail(from: $0) }
        }
    }

    func testDecodeWithSchemaCheckErrorMappingIsExplicit() {
        // A non-empty Decodable is required: an empty struct decodes from any object.
        struct DemandingDummy: Decodable, Sendable { let requiredField: String }
        assertDecodeFailure("not json", expected: .invalidResponse) {
            _ = try SymingestRulesContract.decodeWithSchemaCheck($0) as DemandingDummy
        }
        assertDecodeFailure(#"{"schema_version":1}"#, expected: .invalidResponse) {
            _ = try SymingestRulesContract.decodeWithSchemaCheck($0) as DemandingDummy
        }
        assertDecodeFailure(#"{"schema_version":2}"#, expected: .unsupportedSchema(2)) {
            _ = try SymingestRulesContract.decodeWithSchemaCheck($0) as DemandingDummy
        }
    }

    // MARK: - Optional-field and snake_case decode behavior

    func testDecodeRuleHandlesOptionalCreatedAtAndUnknownKeys() throws {
        // created_at absent -> nil; unknown extra keys are ignored (forward compatible)
        let withoutDate = try SymingestRulesContract.decodeRule(from: Data(#"{"schema_version":1,"rule":{"id":7,"pattern":"invoice","kind":"category","value":"Finance","future_key":1}}"#.utf8))
        XCTAssertNil(withoutDate.rule.createdAt)
        XCTAssertEqual(withoutDate.rule.id, 7)

        let withDate = try SymingestRulesContract.decodeRule(from: Data(#"{"schema_version":1,"rule":{"id":7,"pattern":"invoice","kind":"category","value":"Finance","created_at":"2026-07-12T10:00:00Z"}}"#.utf8))
        XCTAssertEqual(withDate.rule.createdAt, "2026-07-12T10:00:00Z")
    }

    func testDecodeTestHandlesEmptyAndPopulatedMatches() throws {
        let empty = try SymingestRulesContract.decodeTest(from: Data(#"{"schema_version":1,"matches":[]}"#.utf8))
        XCTAssertTrue(empty.matches.isEmpty)

        let populated = try SymingestRulesContract.decodeTest(from: Data(#"{"schema_version":1,"matches":[{"id":7,"pattern":"invoice","kind":"category","value":"Finance"}]}"#.utf8))
        XCTAssertEqual(populated.matches.first, ClassificationRuleMatch(id: 7, pattern: "invoice", kind: "category", value: "Finance"))
    }

    func testDecodeDeleteRoundTrip() throws {
        let deleted = try SymingestRulesContract.decodeDelete(from: Data(#"{"schema_version":1,"id":7,"deleted":true}"#.utf8))
        XCTAssertEqual(deleted.id, 7)
        XCTAssertTrue(deleted.deleted)
    }

    func testDecodeDryRunHandlesSkippedAndEmptyMatches() throws {
        let response = try SymingestRulesContract.decodeDryRun(from: Data("""
        {"schema_version":1,"operation":"dry_run","proposed_rule":{"pattern":"invoice","kind":"tag","value":"Review"},"vault_path":"/vault","total_documents":2,"matched_documents":0,"skipped_documents":2,"matches":[],"skipped":[{"document_id":8,"note_path":"/vault/other.md","reason":"no_match"},{"document_id":9,"note_path":"/vault/more.md","reason":"already_tagged"}]}
        """.utf8))
        XCTAssertTrue(response.matches.isEmpty)
        XCTAssertEqual(response.skipped.count, 2)
        XCTAssertEqual(response.skipped.first?.documentID, 8)
        XCTAssertEqual(response.skipped.first?.reason, "no_match")
        XCTAssertEqual(response.skipped[1].notePath, "/vault/more.md")
        XCTAssertEqual(response.proposedRule, ProposedClassificationRule(pattern: "invoice", kind: "tag", value: "Review"))
    }

    func testDecodeMailDefaultsWarningsAndOptionalAccountFields() throws {
        // warnings key absent -> defaulted to [] by the custom initializer
        let noWarnings = try SymingestRulesContract.decodeMail(from: Data(#"{"schema_version":1,"operation":"list","config_path":"/tmp/config.toml","accounts":[{"host":"imap.example.com","port":993,"username":"daniel","folder":"INBOX","from":["from@x"],"subject":["s"],"has_attachment":true,"action":"move","move_to":"Archive","archive_mail":true}],"reload_required":false}"#.utf8))
        XCTAssertEqual(noWarnings.warnings, [])
        let account = try XCTUnwrap(noWarnings.accounts.first)
        XCTAssertNil(account.id) // id optional, absent -> nil
        XCTAssertNil(account.passwordSecret) // password_secret optional, absent -> nil
        XCTAssertNil(account.passwordSecretKind) // no secret at all -> nil kind (not "plaintext")
        XCTAssertEqual(account.stableID, "daniel@imap.example.com:993/INBOX")
        XCTAssertEqual(account.from, ["from@x"])
        XCTAssertEqual(account.moveTo, "Archive")

        // warnings present are passed through; snake_case keys map to camelCase
        let withWarnings = try SymingestRulesContract.decodeMail(from: Data(#"{"schema_version":1,"operation":"list","config_path":"/c","accounts":[{"id":"acct-1","host":"imap.example.com","port":993,"username":"daniel","password_secret":"symvault://imap/daniel","folder":"INBOX","from":[],"subject":[],"has_attachment":false,"action":"mark_seen","move_to":"","archive_mail":false}],"reload_required":true,"warnings":["legacy config"]}"#.utf8))
        XCTAssertEqual(withWarnings.reloadRequired, true)
        XCTAssertEqual(withWarnings.warnings, ["legacy config"])
        XCTAssertEqual(withWarnings.accounts.first?.passwordSecret, "symvault://imap/daniel")
        XCTAssertEqual(withWarnings.accounts.first?.passwordSecretKind, "symvault")
    }

    // MARK: - Public model initializers

    func testPublicModelInitializersConstructDirectly() {
        // ClassificationRule memberwise init with optional createdAt
        let rule = ClassificationRule(id: 1, pattern: "p", kind: "k", value: "v", createdAt: "2026-07-12T10:00:00Z")
        XCTAssertEqual(rule.id, 1)
        XCTAssertEqual(rule.createdAt, "2026-07-12T10:00:00Z")
        XCTAssertEqual(ClassificationRule(id: 2, pattern: "p", kind: "k", value: "v").createdAt, nil)

        // RulesDryRunMatch: Identifiable id is documentID
        let match = RulesDryRunMatch(documentID: 7, notePath: "/vault/a.md", title: "A", matchedRuleIDs: [3, 4])
        XCTAssertEqual(match.id, 7)
        XCTAssertEqual(match.matchedRuleIDs, [3, 4])

        // RulesDryRunSkipped: Identifiable id is documentID
        let skipped = RulesDryRunSkipped(documentID: 8, notePath: "/vault/b.md", reason: "no_match")
        XCTAssertEqual(skipped.id, 8)
        XCTAssertEqual(skipped.reason, "no_match")

        // RulesDryRunResponse memberwise init
        let response = RulesDryRunResponse(
            schemaVersion: 1,
            operation: "dry_run",
            proposedRule: ProposedClassificationRule(pattern: "p", kind: "k", value: "v"),
            vaultPath: "/vault",
            totalDocuments: 2,
            matchedDocuments: 1,
            skippedDocuments: 1,
            matches: [match],
            skipped: [skipped]
        )
        XCTAssertEqual(response.schemaVersion, 1)
        XCTAssertEqual(response.matches.first?.id, 7)
        XCTAssertEqual(response.skipped.first?.id, 8)
        XCTAssertEqual(response.proposedRule.value, "v")

        // MailConfigurationResponse memberwise init with explicit warnings
        let mail = MailConfigurationResponse(
            schemaVersion: 1,
            operation: "list",
            configPath: "/tmp/config.toml",
            accounts: [],
            reloadRequired: false,
            warnings: ["legacy config"]
        )
        XCTAssertEqual(mail.warnings, ["legacy config"])
        XCTAssertFalse(mail.reloadRequired)
        XCTAssertTrue(mail.accounts.isEmpty)
    }

    // MARK: - Client command construction (fake symingest binary)

    private var tempDirectories: [URL] = []

    override func tearDown() {
        for dir in tempDirectories {
            try? FileManager.default.removeItem(at: dir)
        }
        tempDirectories.removeAll()
        super.tearDown()
    }

    /// Creates a client whose locator resolves to a fake `symingest` shell
    /// script in a fresh temp directory. The script records its argv to
    /// `last-args` and (for mail create/update) its stdin to `last-stdin`,
    /// then answers with a canned schema-version-1 JSON envelope per
    /// subcommand — so command construction is verified end to end through
    /// the existing `CLIRunner` seam without a real binary.
    private func makeFakeBinaryClient(
        vaultPath: String? = nil,
        configPath: String? = nil
    ) throws -> (SymingestRulesClient, URL) {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("symingest-fake-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        tempDirectories.append(dir)

        let binary = dir.appendingPathComponent("symingest")
        try Data(Self.fakeSymingestScript.utf8).write(to: binary)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: binary.path)

        let locator = BinaryLocator(searchPATH: "", extraDirectories: [dir.path])
        let client = SymingestRulesClient(vaultPath: vaultPath, configPath: configPath, locator: locator)
        return (client, dir)
    }

    private static let fakeSymingestScript = #"""
    #!/bin/sh
    DIR="$(cd "$(dirname "$0")" && pwd)"
    printf '%s\n' "$@" > "$DIR/last-args"
    TOP=""
    CMD=""
    for a in "$@"; do
      case "$a" in
        rules) TOP="rules" ;;
        mail) TOP="mail" ;;
        list|add|delete|test|dry-run|create|update) CMD="$a" ;;
      esac
    done
    case "$TOP:$CMD" in
      rules:list)
        printf '%s' '{"schema_version":1,"rules":[{"id":7,"pattern":"invoice","kind":"category","value":"Finance","created_at":"2026-07-12T10:00:00Z"}]}' ;;
      rules:add|rules:update)
        printf '%s' '{"schema_version":1,"rule":{"id":7,"pattern":"invoice","kind":"category","value":"Finance","created_at":null}}' ;;
      rules:delete)
        printf '%s' '{"schema_version":1,"id":7,"deleted":true}' ;;
      rules:test)
        printf '%s' '{"schema_version":1,"matches":[{"id":7,"pattern":"invoice","kind":"category","value":"Finance"}]}' ;;
      rules:dry-run)
        printf '%s' '{"schema_version":1,"operation":"dry_run","proposed_rule":{"pattern":"invoice","kind":"tag","value":"Review"},"vault_path":"/vault","total_documents":2,"matched_documents":1,"skipped_documents":1,"matches":[{"document_id":7,"note_path":"/vault/invoice.md","title":"Invoice","matched_rule_ids":[3]}],"skipped":[{"document_id":8,"note_path":"/vault/other.md","reason":"no_match"}]}' ;;
      mail:list|mail:delete)
        printf '%s' '{"schema_version":1,"operation":"list","config_path":"/tmp/config.toml","accounts":[{"id":"acct-1","host":"imap.example.com","port":993,"username":"daniel","password_secret":"<redacted>","folder":"INBOX","from":[],"subject":[],"has_attachment":false,"action":"mark_seen","move_to":"","archive_mail":false}],"reload_required":false,"warnings":["note"]}' ;;
      mail:create|mail:update)
        cat > "$DIR/last-stdin"
        printf '%s' '{"schema_version":1,"operation":"create","config_path":"/tmp/config.toml","accounts":[{"host":"imap.example.com","port":993,"username":"daniel","folder":"INBOX","from":[],"subject":[],"has_attachment":false,"action":"mark_seen","move_to":"","archive_mail":false}],"reload_required":false,"warnings":[]}' ;;
    esac
    """#

    private func readLastArgs(from dir: URL) throws -> [String] {
        let text = try String(contentsOf: dir.appendingPathComponent("last-args"), encoding: .utf8)
        return text.split(separator: "\n").map(String.init)
    }

    private func readLastStdin(from dir: URL) throws -> Data {
        try Data(contentsOf: dir.appendingPathComponent("last-stdin"))
    }

    func testListRulesConstructsVaultCommand() async throws {
        let (client, dir) = try makeFakeBinaryClient(vaultPath: "/vault")
        let rules = try await client.listRules()
        XCTAssertEqual(try readLastArgs(from: dir), ["rules", "--json", "--vault", "/vault", "list"])
        XCTAssertEqual(rules.first?.id, 7)
        XCTAssertEqual(rules.first?.pattern, "invoice")
    }

    func testListRulesOmitsVaultFlagWhenUnset() async throws {
        let (client, dir) = try makeFakeBinaryClient()
        let rules = try await client.listRules()
        XCTAssertEqual(try readLastArgs(from: dir), ["rules", "--json", "list"])
        XCTAssertEqual(rules.count, 1)
    }

    func testAddRuleConstructsCommand() async throws {
        let (client, dir) = try makeFakeBinaryClient(vaultPath: "/vault")
        let rule = try await client.addRule(pattern: "invoice", kind: "category", value: "Finance")
        XCTAssertEqual(try readLastArgs(from: dir), ["rules", "--json", "--vault", "/vault", "add", "invoice", "category", "Finance"])
        XCTAssertEqual(rule.id, 7)
        XCTAssertNil(rule.createdAt) // canned response has created_at: null
    }

    func testUpdateRuleConstructsCommand() async throws {
        let (client, dir) = try makeFakeBinaryClient(vaultPath: "/vault")
        let rule = try await client.updateRule(id: 7, pattern: "invoice", kind: "category", value: "Finance")
        XCTAssertEqual(try readLastArgs(from: dir), ["rules", "--json", "--vault", "/vault", "update", "7", "invoice", "category", "Finance"])
        XCTAssertEqual(rule.id, 7)
    }

    func testDeleteRuleConstructsCommand() async throws {
        let (client, dir) = try makeFakeBinaryClient(vaultPath: "/vault")
        try await client.deleteRule(id: 7)
        XCTAssertEqual(try readLastArgs(from: dir), ["rules", "--json", "--vault", "/vault", "delete", "7"])
    }

    func testTestRulesPassesTextAsSingleArgument() async throws {
        let (client, dir) = try makeFakeBinaryClient(vaultPath: "/vault")
        let matches = try await client.testRules(text: "remind me about invoices")
        XCTAssertEqual(try readLastArgs(from: dir), ["rules", "--json", "--vault", "/vault", "test", "remind me about invoices"])
        XCTAssertEqual(matches.first?.value, "Finance")
    }

    func testDryRunRuleConstructsCommand() async throws {
        let (client, dir) = try makeFakeBinaryClient(vaultPath: "/vault")
        let response = try await client.dryRunRule(pattern: "invoice", kind: "tag", value: "Review")
        XCTAssertEqual(try readLastArgs(from: dir), ["rules", "--json", "--vault", "/vault", "dry-run", "invoice", "tag", "Review"])
        XCTAssertEqual(response.matchedDocuments, 1)
        XCTAssertEqual(response.skipped.first?.reason, "no_match")
        XCTAssertEqual(response.proposedRule.kind, "tag")
    }

    func testListMailRulesConstructsConfigCommand() async throws {
        let (client, dir) = try makeFakeBinaryClient(configPath: "/tmp/config.toml")
        let accounts = try await client.listMailRules()
        XCTAssertEqual(try readLastArgs(from: dir), ["mail", "--json", "--config", "/tmp/config.toml", "list"])
        XCTAssertEqual(accounts.first?.id, "acct-1")
        XCTAssertEqual(accounts.first?.passwordSecretKind, "redacted")
    }

    func testListMailRulesOmitsConfigFlagWhenUnset() async throws {
        let (client, dir) = try makeFakeBinaryClient()
        let accounts = try await client.listMailRules()
        XCTAssertEqual(try readLastArgs(from: dir), ["mail", "--json", "list"])
        XCTAssertEqual(accounts.count, 1)
    }

    func testCreateMailRuleSendsSnakeCasePayloadOnStdin() async throws {
        let (client, dir) = try makeFakeBinaryClient(configPath: "/tmp/config.toml")
        let account = MailAccount(
            host: "imap.example.com",
            username: "daniel",
            passwordSecret: "symvault://imap/daniel",
            hasAttachment: true,
            moveTo: "Archive",
            archiveMail: true
        )
        let created = try await client.createMailRule(account)
        XCTAssertEqual(try readLastArgs(from: dir), ["mail", "--json", "--config", "/tmp/config.toml", "create"])
        XCTAssertEqual(created.host, "imap.example.com") // canned response account
        XCTAssertEqual(created.username, "daniel")

        let payload = try XCTUnwrap(
            JSONSerialization.jsonObject(with: readLastStdin(from: dir)) as? [String: Any]
        )
        XCTAssertEqual(
            Set(payload.keys),
            Set(["host", "port", "username", "password_secret", "folder", "from", "subject", "has_attachment", "action", "move_to", "archive_mail"])
        )
        XCTAssertEqual(payload["password_secret"] as? String, "symvault://imap/daniel")
        XCTAssertEqual(payload["has_attachment"] as? Bool, true)
        XCTAssertNil(payload["id"]) // nil optional is omitted, not null
    }

    func testUpdateMailRuleSendsPayloadAndIDArgument() async throws {
        let (client, dir) = try makeFakeBinaryClient(configPath: "/tmp/config.toml")
        let account = MailAccount(host: "imap.example.com", username: "daniel")
        let updated = try await client.updateMailRule(id: "daniel@imap.example.com:993/INBOX", account: account)
        XCTAssertEqual(try readLastArgs(from: dir), ["mail", "--json", "--config", "/tmp/config.toml", "update", "daniel@imap.example.com:993/INBOX"])
        XCTAssertEqual(updated.host, "imap.example.com")

        let payload = try XCTUnwrap(
            JSONSerialization.jsonObject(with: readLastStdin(from: dir)) as? [String: Any]
        )
        XCTAssertEqual(payload["host"] as? String, "imap.example.com")
        XCTAssertNil(payload["password_secret"]) // absent optional -> key omitted
    }

    func testDeleteMailRuleConstructsCommand() async throws {
        let (client, dir) = try makeFakeBinaryClient(configPath: "/tmp/config.toml")
        try await client.deleteMailRule(id: "acct-1")
        XCTAssertEqual(try readLastArgs(from: dir), ["mail", "--json", "--config", "/tmp/config.toml", "delete", "acct-1"])
    }
}
