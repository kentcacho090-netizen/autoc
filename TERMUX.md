# AutoC on Termux

AutoC now uses a native terminal UI. It does not require Flask, a browser, or a local web server.

## Fresh install

After clearing Termux data, open Termux and run:

```bash
curl -fsSL https://raw.githubusercontent.com/kentcacho090-netizen/autoc/smart-automation-foundation/install.sh | bash
```

Then start:

```bash
autoc
```

The installer handles the Termux packages, repository checkout, Python environment, native Tesseract OCR, and launcher.

## First test

In the AutoC menu choose:

`[3] Test Android + Screenshot + OCR`

Do this before enabling automation. The detector needs to be calibrated to the actual cloud-phone resolution and game UI.
