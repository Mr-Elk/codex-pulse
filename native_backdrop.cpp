// Windows 11 backdrop, clipped by the compositor before blending with the desktop.
#include <windows.h>
#include <dwmapi.h>
#include <roapi.h>
#include <DispatcherQueue.h>
#include <winrt/Windows.System.h>
#include <winrt/Windows.UI.Composition.h>
#include <winrt/Windows.UI.Composition.Desktop.h>
#include <windows.ui.composition.interop.h>
#include <memory>

using namespace winrt;
using namespace winrt::Windows::UI::Composition;
using namespace winrt::Windows::UI::Composition::Desktop;

struct Runtime {
    winrt::Windows::System::DispatcherQueueController queue{nullptr};
    Compositor compositor{nullptr};
    Runtime() {
        HRESULT hr = RoInitialize(RO_INIT_SINGLETHREADED);
        if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) check_hresult(hr);
        if (!winrt::Windows::System::DispatcherQueue::GetForCurrentThread()) {
            DispatcherQueueOptions options{sizeof(options), DQTYPE_THREAD_CURRENT, DQTAT_COM_NONE};
            check_hresult(CreateDispatcherQueueController(options,
                reinterpret_cast<PDISPATCHERQUEUECONTROLLER*>(put_abi(queue))));
        }
        compositor = Compositor();
    }
};

struct Backdrop {
    DesktopWindowTarget target{nullptr};
    SpriteVisual visual{nullptr};
    CompositionRoundedRectangleGeometry geometry{nullptr};
    Backdrop(HWND hwnd) {
        // Keep the dispatcher alive for the GUI thread's message-pump lifetime.
        static thread_local Runtime* runtime = new Runtime();
        auto& comp = runtime->compositor;
        BOOL enabled = TRUE;
        check_hresult(DwmSetWindowAttribute(hwnd, static_cast<DWMWINDOWATTRIBUTE>(17), &enabled, sizeof(enabled)));
        auto interop = comp.as<ABI::Windows::UI::Composition::Desktop::ICompositorDesktopInterop>();
        check_hresult(interop->CreateDesktopWindowTarget(hwnd, FALSE,
            reinterpret_cast<ABI::Windows::UI::Composition::Desktop::IDesktopWindowTarget**>(put_abi(target))));
        visual = comp.CreateSpriteVisual();
        visual.Brush(comp.CreateHostBackdropBrush());
        geometry = comp.CreateRoundedRectangleGeometry();
        visual.Clip(comp.CreateGeometricClip(geometry));
        target.Root(visual);
    }
    void resize(float width, float height) {
        visual.Size({width, height});
        geometry.Size({width, height});
        geometry.CornerRadius({height / 2, height / 2});
    }
    ~Backdrop() { if (target) target.Root(nullptr); }
};

extern "C" __declspec(dllexport) HRESULT pulse_blur_create(HWND hwnd, void** result) noexcept {
    if (!result) return E_POINTER;
    *result = nullptr;
    try { *result = new Backdrop(hwnd); return S_OK; }
    catch (...) { return to_hresult(); }
}
extern "C" __declspec(dllexport) HRESULT pulse_blur_resize(void* instance, float width, float height) noexcept {
    if (!instance || width < 1 || height < 1) return E_INVALIDARG;
    try { static_cast<Backdrop*>(instance)->resize(width, height); return S_OK; }
    catch (...) { return to_hresult(); }
}
extern "C" __declspec(dllexport) void pulse_blur_destroy(void* instance) noexcept {
    delete static_cast<Backdrop*>(instance);
}
