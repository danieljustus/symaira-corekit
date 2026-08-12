import Foundation

// MARK: - Asset type detection

/// The type of a release asset, used to decide how to install it.
public enum AssetType: Sendable, Equatable {
    /// A standalone binary executable (.tar.gz, raw binary, etc.).
    case binary
    /// A .app bundle inside a DMG disk image.
    case appBundleDMG
    /// A .app bundle inside a ZIP archive.
    case appBundleZip
    /// Asset type could not be determined from the filename.
    case unknown
}

#if os(macOS)
// MARK: - AppInstaller

/// Internal installer for .app bundle release assets (DMG and ZIP paths).
/// `UpdateApplier` delegates its public install entry points here.
enum AppInstaller {

    // MARK: - DMG installation

    /// Mount a DMG, copy the .app bundle to /Applications, and unmount.
    /// Uses `hdiutil` for mount/unmount operations.
    static func installDMG(at dmgURL: URL, assetName: String) throws -> URL {
        guard FileManager.default.isWritableFile(atPath: "/Applications") else {
            throw UpdateApplierError.applicationsNotWritable
        }

        // Mount the DMG.
        let mountResult = try mountDMG(at: dmgURL)
        defer {
            // Always try to unmount, even on error.
            _ = try? unmountDMG(at: mountResult.mountPoint)
        }

        // Find the .app bundle on the mounted volume.
        guard let appURL = findAppBundle(in: mountResult.mountPoint) else {
            throw UpdateApplierError.appBundleNotFound
        }

        let appName = appURL.lastPathComponent
        let destURL = URL(fileURLWithPath: "/Applications").appendingPathComponent(appName)

        // Remove existing .app if present (the running instance is already loaded).
        if FileManager.default.fileExists(atPath: destURL.path) {
            try? FileManager.default.removeItem(at: destURL)
        }

        // Copy the .app to /Applications.
        do {
            try FileManager.default.copyItem(at: appURL, to: destURL)
        } catch {
            throw UpdateApplierError.appBundleCopyFailed(
                "Failed to copy \(appURL.path) to \(destURL.path): \(error.localizedDescription)"
            )
        }

        // Remove quarantine attribute if present.
        _ = try? SubprocessRunner.runChecked(
            executable: URL(fileURLWithPath: "/usr/bin/xattr"),
            arguments: ["-d", "com.apple.quarantine", destURL.path]
        )

        return destURL
    }

    // MARK: - ZIP installation

    /// Extract a ZIP archive, find the .app bundle, and copy it to /Applications.
    static func installZip(at zipURL: URL, assetName: String) throws -> URL {
        guard FileManager.default.isWritableFile(atPath: "/Applications") else {
            throw UpdateApplierError.applicationsNotWritable
        }

        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("updateapply-zip-\(UUID().uuidString)")
        defer {
            try? FileManager.default.removeItem(at: tempDir)
        }

        // Create the temp extraction directory.
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)

        // Use `ditto` for ZIP extraction (more reliable than unzip for .app bundles).
        let dittoResult = try SubprocessRunner.runChecked(
            executable: URL(fileURLWithPath: "/usr/bin/ditto"),
            arguments: ["-xk", zipURL.path, tempDir.path]
        )

        guard dittoResult.exitCode == 0 else {
            throw UpdateApplierError.appBundleCopyFailed(
                "ditto extraction failed with exit code \(dittoResult.exitCode)"
            )
        }

        // Find the .app bundle.
        guard let appURL = findAppBundle(in: tempDir) else {
            throw UpdateApplierError.appBundleNotFound
        }

        let appName = appURL.lastPathComponent
        let destURL = URL(fileURLWithPath: "/Applications").appendingPathComponent(appName)

        // Remove existing .app if present.
        if FileManager.default.fileExists(atPath: destURL.path) {
            try? FileManager.default.removeItem(at: destURL)
        }

        // Copy the .app to /Applications.
        do {
            try FileManager.default.copyItem(at: appURL, to: destURL)
        } catch {
            throw UpdateApplierError.appBundleCopyFailed(
                "Failed to copy \(appURL.path) to \(destURL.path): \(error.localizedDescription)"
            )
        }

        // Remove quarantine attribute.
        _ = try? SubprocessRunner.runChecked(
            executable: URL(fileURLWithPath: "/usr/bin/xattr"),
            arguments: ["-d", "com.apple.quarantine", destURL.path]
        )

        return destURL
    }

    // MARK: - DMG helpers

    /// Mount a DMG using `hdiutil attach`.
    private static func mountDMG(at dmgURL: URL) throws -> UpdateApplier.DMGMountResult {
        // stdout is drained concurrently while the process runs, so the
        // plist output is complete even when it exceeds the 64 KiB pipe
        // buffer, and a hung attach cannot block the update indefinitely.
        let result = try SubprocessRunner.runChecked(
            executable: URL(fileURLWithPath: "/usr/bin/hdiutil"),
            arguments: ["attach", "-nobrowse", "-readonly", "-plist", dmgURL.path]
        )

        guard result.exitCode == 0 else {
            throw UpdateApplierError.dmgMountFailed(
                "hdiutil attach failed with exit code \(result.exitCode)"
            )
        }

        let plist = try PropertyListSerialization.propertyList(from: result.stdout, options: [], format: nil)
        guard let dict = plist as? [String: Any],
              let entities = dict["system-entities"] as? [[String: Any]] else {
            throw UpdateApplierError.dmgMountFailed("Failed to parse hdiutil plist output")
        }

        // Find the mount point entity.
        for entity in entities {
            if let mountPoint = entity["mount-point"] as? String,
               let devEntry = entity["dev-entry"] as? String,
               !mountPoint.isEmpty {
                return UpdateApplier.DMGMountResult(
                    mountPoint: URL(fileURLWithPath: mountPoint),
                    device: devEntry
                )
            }
        }

        throw UpdateApplierError.dmgMountFailed("No mount point found in hdiutil output")
    }

    /// Unmount a DMG using `hdiutil detach`.
    private static func unmountDMG(at mountPoint: URL) throws {
        _ = try SubprocessRunner.runChecked(
            executable: URL(fileURLWithPath: "/usr/bin/hdiutil"),
            arguments: ["detach", mountPoint.path]
        )
    }

    /// Recursively search for a .app bundle in a directory.
    static func findAppBundle(in directory: URL) -> URL? {
        let enumerator = FileManager.default.enumerator(
            at: directory,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles, .skipsPackageDescendants]
        )

        while let url = enumerator?.nextObject() as? URL {
            if url.pathExtension.lowercased() == "app" {
                // Verify it's actually a bundle (has Contents/Info.plist).
                let infoPlist = url.appendingPathComponent("Contents/Info.plist")
                if FileManager.default.fileExists(atPath: infoPlist.path) {
                    return url
                }
            }
        }
        return nil
    }
}
#endif
