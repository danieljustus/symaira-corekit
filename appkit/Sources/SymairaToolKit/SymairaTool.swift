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

    /// When non-`nil`, this tool has been retired from active distribution
    /// and absorbed into another Symaira product. The value is a short
    /// human-readable note naming the replacement (e.g.
    /// `"absorbed into Symaira Desktop"`).
    ///
    /// Consumers use this to display a migration hint instead of offering a
    /// regular install. The Homebrew formulae and casks for deprecated tools
    /// carry Homebrew's own `deprecate!` directive, but app clients cannot read
    /// those, so they consult this field on the registry entry.
    public let deprecated: String?

    public init(
        id: String,
        displayName: String,
        binaryName: String,
        homebrewFormula: String,
        supportsMCP: Bool = true,
        mcpArgs: [String] = ["mcp"],
        deprecated: String? = nil
    ) {
        self.id = id
        self.displayName = displayName
        self.binaryName = binaryName
        self.homebrewFormula = homebrewFormula
        self.supportsMCP = supportsMCP
        self.mcpArgs = mcpArgs
        self.deprecated = deprecated
    }

    public var isDeprecated: Bool { deprecated != nil }
}

/// Registry of all known Symaira CLI tools.
///
/// The `all` array includes deprecated tools (absorbed into other products)
/// for backwards compatibility — they still resolve via `tool(id:)` and
/// retain their Homebrew formulae (which Homebrew marks `deprecate!`).
/// Consumers that present an install UI should filter on `isDeprecated` /
/// `active` to show migration hints instead of a regular install.
///
/// MCP subcommands verified against each repo's cobra commands (2026-08):
/// vault `serve --stdio`, brain/seek/skills/vibecoder `serve`,
/// fetch/scope/fritz/print/ingest/meet `mcp` (symingest since v0.6.0),
/// browse `mcp`, relate `mcp`. `symguard` does not expose an MCP server yet;
/// `symeraseme` is a Python CLI without one; `symbrain`'s `serve` requires
/// a runtime `--profile` argument the static registry cannot express, so it
/// is listed as not MCP-capable until the API can model caller-supplied
/// arguments (see the entry's comment below).
///
/// Deprecated tools (absorbed into other products — see the `deprecated` field):
/// symmemory/symseek/symskills/symguard → symbrain; symfetch → symbrowse;
/// symscope/symtune/symoperate → symcockpit; symprint/symingest/symmeet/
/// symrelate → symdesk.
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
            mcpArgs: ["serve"],
            deprecated: "absorbed into Symaira Brain (symbrain)"
        ),
        SymairaTool(
            id: "symseek",
            displayName: "Symaira Seek",
            binaryName: "symseek",
            homebrewFormula: "danieljustus/tap/symseek",
            mcpArgs: ["serve"],
            deprecated: "absorbed into Symaira Desktop (symdesk)"
        ),
        SymairaTool(
            id: "symfetch",
            displayName: "Symaira Fetch",
            binaryName: "symfetch",
            homebrewFormula: "danieljustus/tap/symfetch",
            mcpArgs: ["mcp"],
            deprecated: "absorbed into Symaira Browse (symbrowse)"
        ),
        SymairaTool(
            id: "symbrowse",
            displayName: "Symaira Browse",
            binaryName: "symbrowse",
            homebrewFormula: "danieljustus/tap/symbrowse",
            mcpArgs: ["mcp"]
        ),
        SymairaTool(
            id: "symscope",
            displayName: "Symaira Scope",
            binaryName: "symscope",
            homebrewFormula: "danieljustus/tap/symscope",
            mcpArgs: ["mcp"],
            deprecated: "absorbed into Symaira Cockpit (symcockpit)"
        ),
        SymairaTool(
            id: "symcockpit",
            displayName: "Symaira Cockpit",
            binaryName: "symcockpit",
            homebrewFormula: "danieljustus/tap/symcockpit",
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
            mcpArgs: ["mcp"],
            deprecated: "absorbed into Symaira Desktop (symdesk)"
        ),
        SymairaTool(
            id: "symskills",
            displayName: "Symaira Skills",
            binaryName: "symskills",
            homebrewFormula: "danieljustus/tap/symskills",
            mcpArgs: ["serve"],
            deprecated: "absorbed into Symaira Brain (symbrain)"
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
            mcpArgs: [],
            deprecated: "absorbed into Symaira Brain (symbrain)"
        ),
        SymairaTool(
            id: "symingest",
            displayName: "Symaira Ingest",
            binaryName: "symingest",
            homebrewFormula: "danieljustus/tap/symingest",
            mcpArgs: ["mcp"],
            deprecated: "absorbed into Symaira Desktop (symdesk)"
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
            mcpArgs: ["mcp"],
            deprecated: "absorbed into Symaira Cockpit (symcockpit)"
        ),
        SymairaTool(
            id: "symoperate",
            displayName: "Symaira Operate",
            binaryName: "symoperate",
            homebrewFormula: "danieljustus/tap/symoperate",
            mcpArgs: ["mcp"],
            deprecated: "absorbed into Symaira Cockpit (symcockpit)"
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
            mcpArgs: ["mcp"],
            deprecated: "absorbed into Symaira Desktop (symdesk)"
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
            mcpArgs: ["mcp"],
            deprecated: "absorbed into Symaira Desktop (symdesk)"
        ),
    ]

    public static func tool(id: String) -> SymairaTool? {
        all.first { $0.id == id }
    }

    /// All registry entries that are not deprecated — i.e. tools that still
    /// have an independent repo and Homebrew formula. Use this when presenting
    /// an install UI so users see only tools they can actually install.
    public static var active: [SymairaTool] {
        all.filter { !$0.isDeprecated }
    }
}
