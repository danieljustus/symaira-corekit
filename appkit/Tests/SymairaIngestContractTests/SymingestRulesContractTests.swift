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
}
