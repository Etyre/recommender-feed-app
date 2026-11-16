// Reading Feed.app: a dedicated macOS window for the Recommender Feed web UI.
//
// It is a thin shell: one window holding a WKWebView pointed at the local API server
// (http://127.0.0.1:8000, the launchd agent com.elityre.recommender-feed.server). All
// app logic stays in backend/ and frontend/. The shell adds what a browser tab gave for
// free and a bare web view does not: menus and shortcuts, external links opening in the
// default browser, JS alert/confirm dialogs, zoom, and a waiting page while the server
// is down.
//
// Config: none of its own (FEED_URL overrides the address, for testing).
// State:  window frame and zoom in UserDefaults (com.elityre.recommender-feed);
//         web storage (the drafts in localStorage) in ~/Library/WebKit/com.elityre.recommender-feed/.
// Log:    ~/Library/Logs/recommender-feed-app.log
// Test:   "Reading Feed.app/Contents/MacOS/ReadingFeed" --test   (no window; prints PASS/FAIL)

import AppKit
import WebKit

let appURL = URL(string: ProcessInfo.processInfo.environment["FEED_URL"] ?? "http://127.0.0.1:8000/")!
let testMode = CommandLine.arguments.contains("--test")
let logPath = NSHomeDirectory() + "/Library/Logs/recommender-feed-app.log"

func log(_ message: String) {
    let stamp = ISO8601DateFormatter().string(from: Date())
    let line = "\(stamp) \(message)\n"
    if testMode { FileHandle.standardError.write(line.data(using: .utf8)!) }
    if let handle = FileHandle(forWritingAtPath: logPath) {
        handle.seekToEndOfFile()
        handle.write(line.data(using: .utf8)!)
        handle.closeFile()
    } else {
        FileManager.default.createFile(atPath: logPath, contents: line.data(using: .utf8))
    }
}

func isAppURL(_ url: URL) -> Bool {
    url.host == appURL.host && url.port == appURL.port
}

let waitingPage = """
<!doctype html><meta charset="utf-8">
<style>
  body { font: 15px -apple-system, sans-serif; color: #555; background: #fff;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
  div { max-width: 30em; text-align: center; line-height: 1.5; }
  code { background: #f0f0f0; padding: 1px 5px; border-radius: 4px; }
  @media (prefers-color-scheme: dark) { body { background: #1f232b; color: #aaa; } code { background: #333; } }
</style>
<div>
  <p><b>Waiting for the feed server…</b></p>
  <p>Nothing is answering at \(appURL.absoluteString) yet. This window retries every second.</p>
  <p>If it stays like this, run <code>./install.sh --app</code> in the project's <code>code</code> folder
     and look at <code>~/Library/Logs/recommender-feed-server.log</code>.</p>
</div>
"""

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var showingWaitingPage = false
    var connectStarted = Date()
    /// index.html as it was when the UI was last loaded; it names the hashed JS/CSS bundles,
    /// so it differs exactly when a newer frontend build is being served.
    var loadedShell: Data?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // WebKit keeps spell check off until the user turns it on from the context menu;
        // the project standard is that prose fields always have it.
        UserDefaults.standard.register(defaults: ["WebContinuousSpellCheckingEnabled": true, "pageZoom": 1.0])

        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()   // persistent: localStorage drafts survive restarts
        webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.pageZoom = UserDefaults.standard.double(forKey: "pageZoom")

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1100, height: 860),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Reading Feed"
        window.isReleasedWhenClosed = false
        window.contentView = webView
        window.center()
        window.setFrameAutosaveName("main")

        if testMode {
            log("test: loading \(appURL.absoluteString)")
        } else {
            buildMenu()
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            log("started")
        }
        connect()
    }

    // Closing the window keeps the app (and the page's state) alive; the dock icon reopens it.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil)
        return true
    }

    // MARK: Server connection

    /// Load the UI if the server answers; otherwise show the waiting page and try again in a second.
    func connect() {
        var request = URLRequest(url: appURL)
        request.timeoutInterval = 2
        request.cachePolicy = .reloadIgnoringLocalCacheData
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                    self.showingWaitingPage = false
                    self.loadedShell = data
                    self.webView.load(URLRequest(url: appURL))
                    return
                }
                if !self.showingWaitingPage {
                    log("server not reachable at \(appURL.absoluteString): \(error?.localizedDescription ?? "bad response")")
                    self.showingWaitingPage = true
                    self.webView.loadHTMLString(waitingPage, baseURL: nil)
                }
                if testMode && Date().timeIntervalSince(self.connectStarted) > 15 {
                    self.finishTest(false, "server never answered at \(appURL.absoluteString)")
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 1) { self.connect() }
            }
        }.resume()
    }

    // A commit rebuilds the frontend behind the app's back (deploy.sh). Pick the new build up
    // when the reader comes back to the app, rather than reloading under them mid-read.
    // Drafts are in localStorage, so a reload loses no typing.
    func applicationDidBecomeActive(_ notification: Notification) {
        guard !showingWaitingPage, let loaded = loadedShell else { return }
        var request = URLRequest(url: appURL)
        request.timeoutInterval = 2
        request.cachePolicy = .reloadIgnoringLocalCacheData
        URLSession.shared.dataTask(with: request) { data, response, _ in
            DispatchQueue.main.async {
                guard let http = response as? HTTPURLResponse, http.statusCode == 200,
                      let data = data, data != loaded, self.loadedShell == loaded else { return }
                log("newer frontend build is being served; reloading")
                self.connect()
            }
        }.resume()
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        guard (error as NSError).code != NSURLErrorCancelled else { return }
        log("page load failed: \(error.localizedDescription)")
        connect()
    }

    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        log("web content process terminated; reloading")
        connect()
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        if testMode, let url = webView.url, isAppURL(url) { checkPage(attempt: 0) }
    }

    // MARK: Links

    // The window only ever shows the feed UI. Any other page (an article, a source) opens
    // in the default browser, where the reader's logins and extensions are.
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url,
              navigationAction.targetFrame?.isMainFrame == true,
              url.scheme == "http" || url.scheme == "https",
              !isAppURL(url) else {
            decisionHandler(.allow)
            return
        }
        NSWorkspace.shared.open(url)
        decisionHandler(.cancel)
    }

    // target="_blank" links (every article link in the feed) arrive here.
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url { NSWorkspace.shared.open(url) }
        return nil
    }

    // MARK: JS dialogs (a bare WKWebView drops alert() and confirm() silently)

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }

    // MARK: Menu actions

    @objc func reload(_ sender: Any?) { connect() }
    @objc func zoomIn(_ sender: Any?) { setZoom(webView.pageZoom + 0.1) }
    @objc func zoomOut(_ sender: Any?) { setZoom(webView.pageZoom - 0.1) }
    @objc func zoomReset(_ sender: Any?) { setZoom(1.0) }
    @objc func openInBrowser(_ sender: Any?) { NSWorkspace.shared.open(appURL) }

    func setZoom(_ zoom: CGFloat) {
        webView.pageZoom = min(max(zoom, 0.5), 3.0)
        UserDefaults.standard.set(Double(webView.pageZoom), forKey: "pageZoom")
    }

    func buildMenu() {
        let main = NSMenu()
        func submenu(_ title: String) -> NSMenu {
            let item = NSMenuItem()
            main.addItem(item)
            let menu = NSMenu(title: title)
            item.submenu = menu
            return menu
        }

        let app = submenu("Reading Feed")
        app.addItem(withTitle: "About Reading Feed", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        app.addItem(.separator())
        app.addItem(withTitle: "Hide Reading Feed", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let others = app.addItem(withTitle: "Hide Others", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        others.keyEquivalentModifierMask = [.command, .option]
        app.addItem(.separator())
        app.addItem(withTitle: "Quit Reading Feed", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")

        // Without an Edit menu, Cmd-C/V/X/Z/A do nothing in the web view's text fields.
        let edit = submenu("Edit")
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(.separator())
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")

        let view = submenu("View")
        view.addItem(withTitle: "Reload", action: #selector(reload(_:)), keyEquivalent: "r")
        view.addItem(.separator())
        view.addItem(withTitle: "Actual Size", action: #selector(zoomReset(_:)), keyEquivalent: "0")
        view.addItem(withTitle: "Zoom In", action: #selector(zoomIn(_:)), keyEquivalent: "+")
        view.addItem(withTitle: "Zoom Out", action: #selector(zoomOut(_:)), keyEquivalent: "-")
        view.addItem(.separator())
        view.addItem(withTitle: "Open in Browser", action: #selector(openInBrowser(_:)), keyEquivalent: "")

        let windowMenu = submenu("Window")
        windowMenu.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        windowMenu.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        NSApp.windowsMenu = windowMenu

        NSApp.mainMenu = main
    }

    // MARK: --test

    /// The React bundle renders after didFinish, so poll until #root has content.
    func checkPage(attempt: Int) {
        let js = """
        (function () {
          var root = document.getElementById('root');
          localStorage.setItem('__shell_test', '1');
          var stored = localStorage.getItem('__shell_test') === '1';
          localStorage.removeItem('__shell_test');
          return JSON.stringify({ title: document.title, rendered: root ? root.childElementCount : 0,
                                  tabs: document.querySelectorAll('button').length, storage: stored });
        })()
        """
        webView.evaluateJavaScript(js) { result, error in
            let text = result as? String ?? "error: \(error?.localizedDescription ?? "no result")"
            let ok = text.contains("\"storage\":true") && !text.contains("\"rendered\":0") && !text.hasPrefix("error")
            if ok { self.finishTest(true, text) }
            else if attempt >= 20 { self.finishTest(false, text) }
            else { DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self.checkPage(attempt: attempt + 1) } }
        }
    }

    func finishTest(_ passed: Bool, _ detail: String) {
        log("test \(passed ? "PASS" : "FAIL"): \(detail)")
        print("\(passed ? "PASS" : "FAIL") \(detail)")
        exit(passed ? 0 : 1)
    }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
// --test runs without a dock icon or window, so it can run while the real app is open.
application.setActivationPolicy(testMode ? .accessory : .regular)
application.run()
