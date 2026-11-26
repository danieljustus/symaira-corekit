import SwiftUI

#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

extension Image {
    /// Static template image of a `SymairaIcon` in its rest pose, for places that
    /// accept only `Image`, such as iOS tab bars (`.tabItem`). The system tints
    /// it like an SF Symbol. Interactive surfaces keep using `SymairaIconView`.
    @MainActor
    public init(symairaIcon icon: SymairaIcon, size: CGFloat = 24, scale: CGFloat = 3) {
        if let image = SymairaIconStill(icon: icon, size: size).templateImage(scale: scale) {
            #if canImport(UIKit)
            self.init(uiImage: image)
            #else
            self.init(nsImage: image)
            #endif
        } else {
            self.init(systemName: "questionmark")
        }
        self = self.renderingMode(.template)
    }
}

/// Rest pose only: no timeline, no hover, so `ImageRenderer` gets one stable frame.
struct SymairaIconStill: View {
    let icon: SymairaIcon
    let size: CGFloat

    #if canImport(UIKit)
    typealias PlatformImage = UIImage
    #else
    typealias PlatformImage = NSImage
    #endif

    func templateImage(scale: CGFloat) -> PlatformImage? {
        let renderer = ImageRenderer(content: self)
        renderer.scale = scale
        #if canImport(UIKit)
        return renderer.uiImage?.withRenderingMode(.alwaysTemplate)
        #else
        let image = renderer.nsImage
        image?.isTemplate = true
        return image
        #endif
    }

    var body: some View {
        Canvas { context, canvasSize in
            for part in icon.spec {
                part.draw(in: &context, size: canvasSize, hover: 0, elapsed: .infinity)
            }
        }
        .frame(width: size, height: size)
        .foregroundStyle(.black)
    }
}

#if os(iOS) || os(tvOS)
extension View {
    /// Mounts the topography behind an iOS or tvOS page, the counterpart of passing
    /// `topography:` to the macOS `SymairaWorkspace`: renderer behind the content,
    /// the shared coordinate space and the `.topoProtected()` environment.
    /// Use it only for the main overview; pass `nil` behind dense lists, tables
    /// and settings (MOTION-1). Low Power Mode, Reduce Motion and the background
    /// scene phase pause the renderer (IOS-4). On tvOS the field follows the focus
    /// engine (TV-2) and is drawn at `SymairaMetrics.platformScale`.
    public func symairaTopography(_ model: SymairaTopoModel?, animationEnabled: Bool = true) -> some View {
        modifier(SymairaTopographyBackground(model: model, animationEnabled: animationEnabled))
    }
}

struct SymairaTopographyBackground: ViewModifier {
    let model: SymairaTopoModel?
    let animationEnabled: Bool

    func body(content: Content) -> some View {
        ZStack {
            if let model {
                SymairaTopoView(model: model, animationEnabled: animationEnabled).ignoresSafeArea()
            } else {
                SymairaTokens.canvas.ignoresSafeArea()
            }
            content.environment(\.symairaTopography, model)
        }
        .coordinateSpace(name: SymairaTopo.space)
    }
}
#endif
