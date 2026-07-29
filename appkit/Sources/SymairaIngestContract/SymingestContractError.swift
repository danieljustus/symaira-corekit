import Foundation

// MARK: - Shared Error

public enum SymingestContractError: Error, LocalizedError, Equatable, Sendable {
    case missingBinary
    case unsupportedSchema(Int)
    case invalidResponse
    case commandFailed(String)

    public var errorDescription: String? {
        switch self {
        case .missingBinary:
            return "symingest is not installed or not on PATH."
        case .unsupportedSchema(let version):
            return "Unsupported symingest schema version \(version)."
        case .invalidResponse:
            return "Invalid symingest JSON response."
        case .commandFailed(let message):
            return message
        }
    }
}

// MARK: - Shared Schema-Checked Decode

/// Decode a versioned JSON response, checking the `schema_version` field first.
/// - Parameters:
///   - data: Raw JSON response data.
///   - expecting: Expected schema version (default 1).
/// - Returns: Decoded value of type `T`.
public func decodeSchemaChecked<T: Decodable>(_ data: Data, expecting version: Int = 1) throws -> T {
    guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let schemaVersion = object["schema_version"] as? Int else {
        throw SymingestContractError.invalidResponse
    }
    guard schemaVersion == version else {
        throw SymingestContractError.unsupportedSchema(schemaVersion)
    }
    do {
        return try JSONDecoder().decode(T.self, from: data)
    } catch let error as SymingestContractError {
        throw error
    } catch {
        throw SymingestContractError.invalidResponse
    }
}
