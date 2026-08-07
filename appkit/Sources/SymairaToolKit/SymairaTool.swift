import Foundation

/// Describes a Symaira CLI tool and how to install and talk to it.
///
/// Extracted from symaira-terminal's `StackKit/SymairaTool.swift`; the
/// registry below is the single source of truth for all clients.
public struct SymairaTool: Equatable, Sendable, Identifiable {
    public let id: String
    public let displayName: String
    public let binaryName: String
    public let homebrewFormula: String
    public let supportsMCP: Bool
    public let mcpArgs: [String]

    public init(
        id: String,
        displayName: String,
        binaryName: String,
        homebrewFormula: String,
        supportsMCP: Bool = true,
        mcpArgs: [String] = ["mcp"]
    ) {
        self.id = id
        self.displayName = displayName
        self.binaryName = binaryName
        self.homebrewFormula = homebrewFormula
        self.supportsMCP = supportsMCP
        self.mcpArgs = mcpArgs
    }
}

/// Registry of all known Symaira CLI tools.
///
/// MCP subcommands verified against each repo's cobra commands (2026-08):
/// vault `serve --stdio`, memory/seek/skills/vibecoder `serve`,
/// fetch/scope/fritz/print/ingest/meet `mcp` (symingest since v0.6.0),
/// relate `mcp`. `symguard` does not expose an MCP server yet;
/// `symeraseme` is a Python CLI without one; `symbrain`'s `serve` requires
/// a runtime `--profile` argument the static registry cannot express, so it
/// is listed as not MCP-capable until the API can model caller-supplied
/// arguments (see the entry's comment below).
public enum SymairaToolRegistry {
    public static let all: [SymairaTool] = [
        SymairaTool(
            id: "symvault",
            displayName: "Symaira Vault",
            binaryName: "symvault",
            homebrewFormula: "danieljustus/tap/symvault",
            mcpArgs: ["serve", "--stdio"]
        ),
        SymairaTool(
            id: "symmemory",
            displayName: "Symaira Memory",
            binaryName: "symmemory",
            homebrewFormula: "danieljustus/tap/symmemory",
            mcpArgs: ["serve"]
        ),
        SymairaTool(
            id: "symseek",
            displayName: "Symaira Seek",
            binaryName: "symseek",
            homebrewFormula: "danieljustus/tap/symseek",
            mcpArgs: ["serve"]
        ),
        SymairaTool(
            id: "symfetch",
            displayName: "Symaira Fetch",
            binaryName: "symfetch",
            homebrewFormula: "danieljustus/tap/symfetch",
            mcpArgs: ["mcp"]
        ),
        SymairaTool(
            id: "symscope",
            displayName: "Symaira Scope",
            binaryName: "symscope",
            homebrewFormula: "danieljustus/tap/symscope",
            mcpArgs: ["mcp"]
        ),
        SymairaTool(
            id: "symfritz",
            displayName: "Symaira Fritz",
            binaryName: "symfritz",
            homebrewFormula: "danieljustus/tap/symfritz",
            mcpArgs: ["mcp"]
        ),
        SymairaTool(
            id: "symprint",
            displayName: "Symaira Print",
            binaryName: "symprint",
            homebrewFormula: "danieljustus/tap/symprint",
            mcpArgs: ["mcp"]
        ),
        SymairaTool(
            id: "symskills",
            displayName: "Symaira Skills",
            binaryName: "symskills",
            homebrewFormula: "danieljustus/tap/symskills",
            mcpArgs: ["serve"]
        ),
        SymairaTool(
            id: "symvibe",
            displayName: "Symaira Vibecoder",
            binaryName: "symvibe",
            homebrewFormula: "danieljustus/tap/symvibe",
            mcpArgs: ["serve"]
        ),
        SymairaTool(
            id: "symguard",
            displayName: "Symaira Guard",
            binaryName: "symguard",
            homebrewFormula: "danieljustus/tap/symguard",
            supportsMCP: false,
            mcpArgs: []
        ),
        SymairaTool(
            id: "symingest",
            displayName: "Symaira Ingest",
            binaryName: "symingest",
            homebrewFormula: "danieljustus/tap/symingest",
            mcpArgs: ["mcp"]
        ),
        SymairaTool(
            id: "symeraseme",
            displayName: "Symaira EraseMe",
            binaryName: "symeraseme",
            homebrewFormula: "danieljustus/tap/symeraseme",
            supportsMCP: false,
            mcpArgs: []
        ),
        SymairaTool(
            id: "symtune",
            displayName: "Symaira Tune",
            binaryName: "symtune",
            homebrewFormula: "danieljustus/tap/symtune",
            mcpArgs: ["mcp"]
        ),
        SymairaTool(
            id: "symoperate",
            displayName: "Symaira Operate",
            binaryName: "symoperate",
            homebrewFormula: "danieljustus/tap/symoperate",
            mcpArgs: ["mcp"]
        ),
        SymairaTool(
            id: "symdesk",
            displayName: "Symaira Desktop",
            binaryName: "symdesk",
            homebrewFormula: "danieljustus/tap/symdesk",
            mcpArgs: ["mcp"]
        ),
        SymairaTool(
            id: "symmeet",
            displayName: "Symaira Meet",
            binaryName: "symmeet",
            homebrewFormula: "danieljustus/tap/symmeet",
            mcpArgs: ["mcp"]
        ),
        // symbrain's MCP server (`serve`) requires a caller-supplied
        // `--profile <name>` argument; the static registry cannot express a
        // required runtime parameter, so the entry honestly declares no MCP
        // support rather than advertising an invocation that always fails.
        // Consumers must supply the profile themselves at launch time.
        SymairaTool(
            id: "symbrain",
            displayName: "Symaira Brain",
            binaryName: "symbrain",
            homebrewFormula: "danieljustus/tap/symbrain",
            supportsMCP: false,
            mcpArgs: []
        ),
        SymairaTool(
            id: "symrelate",
            displayName: "Symaira Relate",
            binaryName: "symrelate",
            homebrewFormula: "danieljustus/tap/symrelate",
            mcpArgs: ["mcp"]
        ),
    ]

    public static func tool(id: String) -> SymairaTool? {
        all.first { $0.id == id }
    }
}
