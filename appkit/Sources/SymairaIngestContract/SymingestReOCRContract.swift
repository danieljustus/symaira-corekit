import Foundation
import SymairaToolKit
import SymairaCLIRunner

// MARK: - Types

public struct ReOCRError: Codable, Equatable, Sendable {
    public let code: String
    public let message: String

    public init(code: String, message: String) {
        self.code = code
        self.message = message
    }
}

public struct ReOCRResponse: Codable, Equatable, Sendable {
    public let schemaVersion: Int
    public let documentID: Int64
    public let jobID: Int64
    public let status: String
    public let outputPath: String
    public let error: ReOCRError?

    public init(
        schemaVersion: Int,
        documentID: Int64,
        jobID: Int64,
        status: String,
        outputPath: String,
        error: ReOCRError? = nil
    ) {
        self.schemaVersion = schemaVersion
        self.documentID = documentID
        self.jobID = jobID
        self.status = status
        self.outputPath = outputPath
        self.error = error
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case documentID = "document_id"
        case jobID = "job_id"
        case status
        case outputPath = "output_path"
        case error
    }
}

public enum ReOCRRequest: Equatable, Sendable {
    case documentID(Int64)
    case archivePath(String)

    public var documentID: Int64? {
        switch self {
        case .documentID(let id): return id
        case .archivePath: return nil
        }
    }

    public var archivePath: String? {
        switch self {
        case .documentID: return nil
        case .archivePath(let path): return path
        }
    }
}

public typealias ReOCRContractError = SymingestContractError

// MARK: - Envelope

public enum ReOCRContract {
    public static func decode(from data: Data) throws -> ReOCRResponse {
        do {
            return try JSONDecoder().decode(ReOCRResponse.self, from: data)
        } catch {
            throw ReOCRContractError.invalidResponse
        }
    }

    public static func decodeWithSchemaCheck(from data: Data) throws -> ReOCRResponse {
        try decodeSchemaChecked(data)
    }
}

// MARK: - Client

public protocol ReOCRClient: Sendable {
    func reprocess(documentID: Int64) async throws -> ReOCRResponse
    func reprocess(archivePath: String) async throws -> ReOCRResponse
}

#if os(macOS)
public struct SymingestReOCRClient: ReOCRClient, Sendable {
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
        let tool = try SymairaToolRegistry.ingestTool
        guard let located = locator.locate(tool.binaryName) else {
            throw ReOCRContractError.missingBinary
        }
        return located.url
    }

    private func reocrArguments(_ request: ReOCRRequest) -> [String] {
        var args = ["reocr", "--json"]
        if let configPath, !configPath.isEmpty { args.append(contentsOf: ["-db", configPath]) }
        if let vaultPath, !vaultPath.isEmpty { args.append(contentsOf: ["-vault", vaultPath]) }
        switch request {
        case .documentID(let id):
            args.append(contentsOf: ["--document-id", String(id)])
        case .archivePath(let path):
            args.append(path)
        }
        return args
    }

    private func run(_ args: [String]) async throws -> Data {
        let url = try locate()
        let data = try await runner.runChecked(url, arguments: args, timeout: 60)
        return data
    }

    public func reprocess(documentID: Int64) async throws -> ReOCRResponse {
        try await ReOCRContract.decodeWithSchemaCheck(from: run(reocrArguments(.documentID(documentID))))
    }

    public func reprocess(archivePath: String) async throws -> ReOCRResponse {
        try await ReOCRContract.decodeWithSchemaCheck(from: run(reocrArguments(.archivePath(archivePath))))
    }
}
#endif
