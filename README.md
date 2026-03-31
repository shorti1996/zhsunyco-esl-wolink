# Wolink BLE E-Paper Labels

Home Assistant integration for Wolink BLE electronic shelf labels (ESL). Discovers, connects to, and pushes custom-rendered content to e-paper price tags over Bluetooth Low Energy — fully local, no cloud required.

## Features

- **Auto-discovery** — detects nearby Wolink ESL devices via Bluetooth advertisement
- **Multiple device models** — 2.90", 2.13", 1.54", and other form factors including multi-color (red, yellow) displays
- **`drawcustom` service** — render layouts from a list of drawing elements (text, icons, shapes, QR/barcodes, images, charts, progress bars) with Jinja2 template support
- **`send_image` service** — push an image file directly with optional Floyd-Steinberg dithering
- **Live preview** — image entity shows the current display content as PNG
- **Robust BLE** — dual-path retry with advertisement-window awareness for reliable writes to sleeping devices

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| Display | Image | Live preview of current content; exposes `display_width`/`display_height` attributes |
| Refresh Display | Button | Re-sends the last cached image |
| Display Status | Sensor | idle / sending / success / error |
| Display Resolution | Sensor | e.g. "296x128" |
| Last Refresh | Sensor | Timestamp of last successful write |

## Services

### `wolink_esl.drawcustom`

Renders a payload of drawing elements and pushes the result to the display. Compatible with the [E-Ink Display Manager](https://github.com/shorti1996/eink-display-manager) orchestration layer and the [OpenEPaperLink](https://github.com/OpenEPaperLink/Home_Assistant_Integration) drawcustom element format.

Supported element types: `text`, `multiline`, `icon` (MDI), `line`, `rectangle`, `ellipse`, `circle`, `arc`, `dlimg`, `qrcode`, `barcode`, `progress_bar`, `diagram`, `plot`, `rectangle_pattern`.

### `wolink_esl.send_image`

Sends an image file to the display with optional dithering.

## Installation

Requires [HACS](https://hacs.xyz/docs/use/) (Home Assistant Community Store).

1. [Add this repository as a custom repository](https://hacs.xyz/docs/faq/custom_repositories/) in HACS (category: **Integration**).
2. Install **Wolink BLE E-Paper Labels** from the HACS store.
3. Restart Home Assistant.
4. The integration auto-discovers nearby Wolink ESL devices via Bluetooth, or you can add one manually by MAC address.

## Source

This repository is auto-published from the monorepo: [shorti1996/zhsunyco-eink](https://github.com/shorti1996/zhsunyco-eink)
