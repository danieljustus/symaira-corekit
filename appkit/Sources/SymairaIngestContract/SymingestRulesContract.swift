import Foundation
import SymairaToolKit
import SymairaCLIRunner

// MARK: - Types

public struct ClassificationRule: Codable, Equatable, Identifiable, Sendable {
    public let id: Int64
    public let pattern: String
    public let kind: String
    public let value: String
    public let createdAt: String?

    public init(id: Int64, pattern: String, kind: String, value: String, createdAt: String? = nil) {
        self.id = id
        self.pattern = pattern
        self.kind = kind
        self.value = value
        self.createdAt = createdAt
    }
}

public struct ClassificationRuleMatch: Codable, Equatable, Identifiable, Sendable {
    public let id: Int64
    public let pattern: String
    public let kind: String
    public let value: String

    public init(id: Int64, pattern: String, kind: String, value: String) {
        self.id = id
        self.pattern = pattern
        self.kind = kind
        self.value = value
    }
}

public struct ProposedClassificationRule: Codable, Equatable, Sendable {
    public let pattern: String
    public let kind: String
    public let value: String

    public init(pattern: String, kind: String, value: String) {
        self.pattern = pattern
        self.kind = kind
        self.value = value
    }
}

public struct RulesDryRunMatch: Codable, Equatable, Identifiable, Sendable {
    public var id: Int64 { documentID }
    public let documentID: Int64
    public let notePath: String
    public let title: String
    public let matchedRuleIDs: [Int64]

    public init(documentID: Int64, notePath: String, title: String, matchedRuleIDs: [Int64]) {
        self.documentID = documentID
        self.notePath = notePath
        self.title = title
        self.matchedRuleIDs = matchedRuleIDs
    }
}

public struct RulesDryRunSkipped: Codable, Equatable, Identifiable, Sendable {
    public var id: Int64 { documentID }
    public let documentID: Int64
    public let notePath: String
    public let reason: String

    public init(documentID: Int64, notePath: String, reason: String) {
        self.documentID = documentID
        self.notePath = notePath
        self.reason = reason
    }
}

public struct RulesDryRunResponse: Codable, Equatable, Sendable {
    public let schemaVersion: Int
    public let operation: String
    public let proposedRule: ProposedClassificationRule
    public let vaultPath: String
    public let totalDocuments: Int
    public let matchedDocuments: Int
    public let skippedDocuments: Int
    public let matches: [RulesDryRunMatch]
    public let skipped: [RulesDryRunSkipped]

    public init(
        schemaVersion: Int,
        operation: String,
        proposedRule: ProposedClassificationRule,
        vaultPath: String,
        totalDocuments: Int,
        matchedDocuments: Int,
        skippedDocuments: Int,
        matches: [RulesDryRunMatch],
        skipped: [RulesDryRunSkipped]
    ) {
        self.schemaVersion = schemaVersion
        self.operation = operation
        self.proposedRule = proposedRule
        self.vaultPath = vaultPath
        self.totalDocuments = totalDocuments
        self.matchedDocuments = matchedDocuments
        self.skippedDocuments = skippedDocuments
        self.matches = matches
        self.skipped = skipped
    }
}

public struct MailAccount: Codable, Equatable, Sendable {
    public let id: String?
    public let host: String
    public let port: Int
    public let username: String
    public let passwordSecret: String?
    public let folder: String
    public let from: [String]
    public let subject: [String]
    public let hasAttachment: Bool
    public let action: String
    public let moveTo: String
    public let archiveMail: Bool

    public var stableID: String {
        id ?? "\(username)@\(host):\(port)/\(folder)"
    }

    public var passwordSecretKind: String? {
        guard let secret = passwordSecret else { return nil }
        if secret.hasPrefix("symvault://") { return "symvault" }
        if secret == "<redacted>" { return "redacted" }
        return "plaintext"
    }

    public init(
        id: String? = nil,
        host: String,
        port: Int = 993,
        username: String,
        passwordSecret: String? = nil,
        folder: String = "INBOX",
        from: [String] = [],
        subject: [String] = [],
        hasAttachment: Bool = false,
        action: String = "mark_seen",
        moveTo: String = "",
        archiveMail: Bool = false
    ) {
        self.id = id
        self.host = host
        self.port = port
        self.username = username
        self.passwordSecret = passwordSecret
        self.folder = folder
        self.from = from
        self.subject = subject
        self.hasAttachment = hasAttachment
        self.action = action
        self.moveTo = moveTo
        self.archiveMail = archiveMail
    }
}

public struct MailConfigurationResponse: Codable, Equatable, Sendable {
    public let schemaVersion: Int
    public let operation: String
    public let configPath: String
    public let accounts: [MailAccount]
    public let reloadRequired: Bool
    public let warnings: [String]

    public init(
        schemaVersion: Int,
        operation: String,
        configPath: String,
        accounts: [MailAccount],
        reloadRequired: Bool,
        warnings: [String] = []
    ) {
        self.schemaVersion = schemaVersion
        self.operation = operation
        self.configPath = configPath
        self.accounts = accounts
        self.reloadRequired = reloadRequired
        self.warnings = warnings
    }
}

public enum SymingestRulesError: Error, LocalizedError, Equatable, Sendable {
    case missingBinary
    case unsupportedSchema(Int)
    case invalidResponse
    case commandFailed(String)

    public var errorDescription: String? {
        switch self {
        case .missingBinary:
            return "symingest is not installed or not on PATH."
        case .unsupportedSchema(let version):
            return "Unsupported symingest rules schema version \(version)."
        case .invalidResponse:
            return "Invalid symingest rules JSON response."
        case .commandFailed(let message):
            return message
        }
    }
}

// MARK: - Envelopes

public enum SymingestRulesContract {
    public struct ListResponse: Codable, Sendable {
        public let schemaVersion: Int
        public let rules: [ClassificationRule]
    }

    public struct RuleResponse: Codable, Sendable {
        public let schemaVersion: Int
        public let rule: ClassificationRule
    }

    public struct TestResponse: Codable, Sendable {
        public let schemaVersion: Int
        public let matches: [ClassificationRuleMatch]
    }

    public struct DeleteResponse: Codable, Sendable {
        public let schemaVersion: Int
        public let id: Int64
        public let deleted: Bool
    }

    public static func decodeList(from data: Data) throws -> ListResponse {
        try decoded(data)
    }

    public static func decodeRule(from data: Data) throws -> RuleResponse {
        try decoded(data)
    }

    public static func decodeTest(from data: Data) throws -> TestResponse {
        try decoded(data)
    }

    public static func decodeDelete(from data: Data) throws -> DeleteResponse {
        try decoded(data)
    }

    public static func decodeDryRun(from data: Data) throws -> RulesDryRunResponse {
        try decoded(data)
    }

    public static func decodeMail(from data: Data) throws -> MailConfigurationResponse {
        try decoded(data)
    }

    private static func decoded<T: Decodable>(
        _ data: Data
    ) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw SymingestRulesError.invalidResponse
        }
    }

    private static func decodeSchemaVersion(from data: Data) throws -> Int {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let version = object["schema_version"] as? Int else {
            throw SymingestRulesError.invalidResponse
        }
        return version
    }

    public static func decodeWithSchemaCheck<T: Decodable>(_ data: Data) throws -> T {
        let version = try decodeSchemaVersion(from: data)
        guard version == 1 else {
            throw SymingestRulesError.unsupportedSchema(version)
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw SymingestRulesError.invalidResponse
        }
    }
}

// MARK: - Client

public protocol ClassificationRulesClient: Sendable {
    func listRules() async throws -> [ClassificationRule]
    func addRule(pattern: String, kind: String, value: String) async throws -> ClassificationRule
    func updateRule(id: Int64, pattern: String, kind: String, value: String) async throws -> ClassificationRule
    func deleteRule(id: Int64) async throws
    func testRules(text: String) async throws -> [ClassificationRuleMatch]
    func dryRunRule(pattern: String, kind: String, value: String) async throws -> RulesDryRunResponse
    func listMailRules() async throws -> [MailAccount]
    func createMailRule(_ account: MailAccount) async throws -> MailAccount
    func updateMailRule(id: String, account: MailAccount) async throws -> MailAccount
    func deleteMailRule(id: String) async throws
}

public struct SymingestRulesClient: ClassificationRulesClient, Sendable {
    private let locator: BinaryLocator
    private let runner: CLIRunner
    private let vaultPath: String?
    private let configPath: String?

    public init(
        vaultPath: String? = nil,
        configPath: String? = nil,
        locator: BinaryLocator = BinaryLocator(),
        runner: CLIRunner = CLIRunner()
    ) {
        self.vaultPath = vaultPath
        self.configPath = configPath
        self.locator = locator
        self.runner = runner
    }

    private func locate() throws -> URL {
        let tool = SymairaToolRegistry.ingestTool
        guard let located = locator.locate(tool.binaryName) else {
            throw SymingestRulesError.missingBinary
        }
        return located.url
    }

    private func ruleArguments(_ command: String...) -> [String] {
        var args = ["rules", "--json"]
        if let vaultPath, !vaultPath.isEmpty { args.append(contentsOf: ["--vault", vaultPath]) }
        args.append(contentsOf: command)
        return args
    }

    private func mailArguments(_ command: String...) -> [String] {
        var args = ["mail", "--json"]
        if let configPath, !configPath.isEmpty { args.append(contentsOf: ["--config", configPath]) }
        args.append(contentsOf: command)
        return args
    }

    private func run(_ args: [String], stdin: Data? = nil) async throws -> Data {
        let url = try locate()
        let data = try await runner.runChecked(url, arguments: args, stdin: stdin, timeout: 60)
        return data
    }

    public func listRules() async throws -> [ClassificationRule] {
        try await SymingestRulesContract.decodeList(from: run(ruleArguments("list"))).rules
    }

    public func addRule(pattern: String, kind: String, value: String) async throws -> ClassificationRule {
        try await SymingestRulesContract.decodeRule(from: run(ruleArguments("add", pattern, kind, value))).rule
    }

    public func updateRule(id: Int64, pattern: String, kind: String, value: String) async throws -> ClassificationRule {
        try await SymingestRulesContract.decodeRule(from: run(ruleArguments("update", String(id), pattern, kind, value))).rule
    }

    public func deleteRule(id: Int64) async throws {
        _ = try await SymingestRulesContract.decodeDelete(from: run(ruleArguments("delete", String(id))))
    }

    public func testRules(text: String) async throws -> [ClassificationRuleMatch] {
        try await SymingestRulesContract.decodeTest(from: run(ruleArguments("test", text))).matches
    }

    public func dryRunRule(pattern: String, kind: String, value: String) async throws -> RulesDryRunResponse {
        try await SymingestRulesContract.decodeDryRun(from: run(ruleArguments("dry-run", pattern, kind, value)))
    }

    public func listMailRules() async throws -> [MailAccount] {
        try await SymingestRulesContract.decodeMail(from: run(mailArguments("list"))).accounts
    }

    public func createMailRule(_ account: MailAccount) async throws -> MailAccount {
        let payload = try JSONEncoder().encode(account)
        return try await SymingestRulesContract.decodeMail(from: run(mailArguments("create"), stdin: payload)).accounts.first ?? account
    }

    public func updateMailRule(id: String, account: MailAccount) async throws -> MailAccount {
        let payload = try JSONEncoder().encode(account)
        return try await SymingestRulesContract.decodeMail(from: run(mailArguments("update", id), stdin: payload)).accounts.first ?? account
    }

    public func deleteMailRule(id: String) async throws {
        _ = try await SymingestRulesContract.decodeMail(from: run(mailArguments("delete", id)))
    }
}

public extension SymairaToolRegistry {
    static var ingestTool: SymairaTool {
        all.first { $0.id == "symingest" }!
    }
}
