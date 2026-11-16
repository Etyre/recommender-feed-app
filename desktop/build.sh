#!/bin/zsh
# Build "Reading Feed.app" (the desktop window for the feed, desktop/main.swift) into
# desktop/build and install it to ~/Applications. Idempotent; safe to rerun.
# The app only shows what the local server serves: ./install.sh --app also installs that.
# A running copy keeps the old code until it is quit and reopened.
set -euo pipefail
cd "$(dirname "$0")"
NAME="Reading Feed"
APP="build/$NAME.app"
rm -rf build && mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" build/icon.iconset

swiftc -O -swift-version 5 -target arm64-apple-macosx14.0 -framework AppKit -framework WebKit \
  main.swift -o "$APP/Contents/MacOS/ReadingFeed"

# Icon: the web app's own 512px icon (sizes above 512 are upscaled).
for s in 16 32 128 256 512; do
  sips -z $s $s ../frontend/public/icon-512.png --out build/icon.iconset/icon_${s}x${s}.png >/dev/null
  d=$((s*2)); sips -z $d $d ../frontend/public/icon-512.png --out build/icon.iconset/icon_${s}x${s}@2x.png >/dev/null
done
iconutil -c icns build/icon.iconset -o "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>$NAME</string>
  <key>CFBundleDisplayName</key><string>$NAME</string>
  <key>CFBundleIdentifier</key><string>com.elityre.recommender-feed</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleExecutable</key><string>ReadingFeed</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.news</string>
  <key>NSHighResolutionCapable</key><true/>
  <!-- The UI is plain http on 127.0.0.1; App Transport Security blocks that without this. -->
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
PLIST

xattr -cr "$APP"
codesign --force --sign - --identifier com.elityre.recommender-feed "$APP"
mkdir -p ~/Applications
rm -rf ~/Applications/"$NAME.app"
cp -R "$APP" ~/Applications/
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f ~/Applications/"$NAME.app" >/dev/null 2>&1 || true
echo "Installed ~/Applications/$NAME.app"
