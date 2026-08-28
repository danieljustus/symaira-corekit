import Foundation
import SymairaCLIRunner

/// Machine-readable error categories shared with corekit's contract.
public enum SymairaProviderErrorCode: String, Codable, Sendable, Equatable {
    case authFailure = "auth_failure"
    case rateLimited = "rate_limited"
    case contextOverflow = "context_overflow"
    case modelNotFound = "model_not_found"
    case transportError = "transport_error"
    case providerError = "provider_error"
}

public struct SymairaProviderErrorDescriptor: Codable, Sendable, Equatable {
    public let code: SymairaProviderErrorCode
    public let meaning: String
    public let exitCode: String
    public let retryable: Bool

    private enum CodingKeys: String, CodingKey {
        case code, meaning, exitCode = "exit_code", retryable
    }
}

/// The error taxonomy bundled from corekit's cross-language contract.
public struct SymairaProviderErrorCatalog: Codable, Sendable, Equatable {
    public let schemaVersion: Int
    public let errors: [SymairaProviderErrorDescriptor]

    public init(schemaVersion: Int, errors: [SymairaProviderErrorDescriptor]) throws {
        guard schemaVersion == 1 else {
            throw SymairaProviderErrorCatalogError.unsupportedSchema(schemaVersion)
        }
        let codes = errors.map(\.code)
        guard Set(codes).count == codes.count else {
            throw SymairaProviderErrorCatalogError.duplicateCode
        }
        self.schemaVersion = schemaVersion
        self.errors = errors
    }

    public static let bundled: SymairaProviderErrorCatalog = {
        do {
            return try load()
        } catch {
            preconditionFailure("Unable to load SymairaProviderKit error descriptors: \(error)")
        }
    }()

    public static func load() throws -> SymairaProviderErrorCatalog {
        try load(bundle: Bundle.module)
    }

    public static func load(bundle: Bundle) throws -> SymairaProviderErrorCatalog {
        guard let url = bundle.url(forResource: "llm_errors", withExtension: "json") else {
            throw SymairaProviderErrorCatalogError.missingResource
        }
        do {
            let value = try JSONDecoder().decode(Resource.self, from: Data(contentsOf: url))
            return try SymairaProviderErrorCatalog(schemaVersion: value.schemaVersion, errors: value.errors)
        } catch let error as SymairaProviderErrorCatalogError {
            throw error
        } catch {
            throw SymairaProviderErrorCatalogError.invalidData
        }
    }

    public init(data: Data) throws {
        do {
            let value = try JSONDecoder().decode(Resource.self, from: data)
            try self.init(schemaVersion: value.schemaVersion, errors: value.errors)
        } catch let error as SymairaProviderErrorCatalogError {
            throw error
        } catch {
            throw SymairaProviderErrorCatalogError.invalidData
        }
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        try self.init(
            schemaVersion: container.decode(Int.self, forKey: .schemaVersion),
            errors: container.decode([SymairaProviderErrorDescriptor].self, forKey: .errors)
        )
    }

    private struct Resource: Decodable {
        let schemaVersion: Int
        let errors: [SymairaProviderErrorDescriptor]

        private enum CodingKeys: String, CodingKey {
            case schemaVersion = "schema_version", errors
        }
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version", errors
    }
}

public enum SymairaProviderErrorCatalogError: Error, LocalizedError, Sendable, Equatable {
    case missingResource
    case invalidData
    case unsupportedSchema(Int)
    case duplicateCode

    public var errorDescription: String? {
        switch self {
        case .missingResource:
            return "The bundled LLM error taxonomy is missing."
        case .invalidData:
            return "The bundled LLM error taxonomy is invalid."
        case .unsupportedSchema(let version):
            return "Unsupported LLM error taxonomy schema version \(version)."
        case .duplicateCode:
            return "The LLM error taxonomy contains duplicate codes."
        }
    }
}

/// A provider failure with a stable category and a redacted diagnostic.
public struct SymairaProviderError: Error, LocalizedError, Codable, Sendable, Equatable {
    public let code: SymairaProviderErrorCode
    public let message: String
    public let statusCode: Int?
    public let retryAfter: TimeInterval?
    public let bodyExcerpt: String?

    public init(
        code: SymairaProviderErrorCode,
        message: String,
        statusCode: Int? = nil,
        retryAfter: TimeInterval? = nil,
        bodyExcerpt: String? = nil
    ) {
        self.code = code
        self.message = SymairaSecretRedactor.redact(message)
        self.statusCode = statusCode
        self.retryAfter = retryAfter
        self.bodyExcerpt = bodyExcerpt.map { SymairaSecretRedactor.redact($0) }
    }

    public var errorDescription: String? {
        var result = message
        if let statusCode {
            result += " (HTTP \(statusCode))"
        }
        return SymairaSecretRedactor.redact(result)
    }

    private enum CodingKeys: String, CodingKey {
        case code, message, statusCode = "status_code", retryAfter = "retry_after", bodyExcerpt = "body_excerpt"
    }
}

/// Maps HTTP and transport failures to the shared provider error taxonomy.
public enum SymairaProviderErrorMapper {
    public static func http(
        statusCode: Int,
        headers: [String: String] = [:],
        body: Data = Data()
    ) -> SymairaProviderError {
        let excerpt = bodyExcerpt(body)
        let lowerBody = excerpt.lowercased()
        let retryAfter = Double(headers.first { $0.key.caseInsensitiveCompare("retry-after") == .orderedSame }?.value ?? "")

        if statusCode == 401 || statusCode == 403 {
            return SymairaProviderError(
                code: .authFailure,
                message: "The provider rejected the credential.",
                statusCode: statusCode,
                bodyExcerpt: excerpt
            )
        }
        if statusCode == 429 {
            return SymairaProviderError(
                code: .rateLimited,
                message: "The provider rate-limited the request.",
                statusCode: statusCode,
                retryAfter: retryAfter,
                bodyExcerpt: excerpt
            )
        }
        if statusCode == 404 {
            return SymairaProviderError(
                code: .modelNotFound,
                message: "The provider endpoint or model was not found.",
                statusCode: statusCode,
                bodyExcerpt: excerpt
            )
        }
        if statusCode == 400 && containsContextOverflowSignature(lowerBody) {
            return SymairaProviderError(
                code: .contextOverflow,
                message: "The request exceeds the model context window.",
                statusCode: statusCode,
                bodyExcerpt: excerpt
            )
        }
        return SymairaProviderError(
            code: .providerError,
            message: "The provider rejected the request.",
            statusCode: statusCode,
            bodyExcerpt: excerpt
        )
    }

    public static func transport(_ error: Error) -> SymairaProviderError {
        let message: String
        if let urlError = error as? URLError {
            switch urlError.code {
            case .timedOut:
                message = "The provider request timed out."
            case .cannotFindHost, .dnsLookupFailed:
                message = "The provider host could not be resolved."
            case .appTransportSecurityRequiresSecureConnection:
                message = "The provider endpoint requires a secure connection."
            default:
                message = "The provider request could not be completed."
            }
        } else {
            message = "The provider request could not be completed."
        }
        return SymairaProviderError(code: .transportError, message: message)
    }

    public static func invalidConfiguration(_ message: String) -> SymairaProviderError {
        SymairaProviderError(code: .providerError, message: message)
    }

    private static func containsContextOverflowSignature(_ body: String) -> Bool {
        [
            "context length",
            "context window",
            "maximum context",
            "max context",
            "too many tokens",
            "prompt is too long",
            "token limit",
        ].contains { body.contains($0) }
    }

    private static func bodyExcerpt(_ data: Data) -> String {
        let text = String(decoding: data, as: UTF8.self)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard text.count > 512 else { return SymairaSecretRedactor.redact(text) }
        let end = text.index(text.startIndex, offsetBy: 512)
        return SymairaSecretRedactor.redact(String(text[..<end])) + "…"
    }
}
