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
        let renderer = ImageRenderer(content: SymairaIconStill(icon: icon, size: size))
        renderer.scale = scale
        #if canImport(UIKit)
        if let image = renderer.uiImage {
            self.init(uiImage: image)
        } else {
            self.init(systemName: "questionmark")
        }
        #else
        if let image = renderer.nsImage {
            self.init(nsImage: image)
        } else {
            self.init(systemName: "questionmark")
        }
        #endif
        self = self.renderingMode(.template)
    }
}

/// Rest pose only: no timeline, no hover, so `ImageRenderer` gets one stable frame.
struct SymairaIconStill: View {
    let icon: SymairaIcon
    let size: CGFloat
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

#if os(iOS)
extension View {
    /// Mounts the topography behind an iOS page, the counterpart of passing
    /// `topography:` to the macOS `SymairaWorkspace`: renderer behind the content,
    /// the shared coordinate space and the `.topoProtected()` environment.
    /// Use it only for the main overview; pass `nil` behind dense lists, tables
    /// and settings (MOTION-1). Low Power Mode, Reduce Motion and the background
    /// scene phase pause the renderer (IOS-4).
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
