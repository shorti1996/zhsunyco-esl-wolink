// Wolink ESL Display — Lovelace preview card
import { LitElement, html, css } from "lit";

class WolinkEslCard extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _config: { type: Object },
      _payloadText: { type: String },
      _sending: { type: Boolean },
      _error: { type: String },
      _lastSent: { type: String },
      _background: { type: String },
      _rotation: { type: Number },
      _cacheBuster: { type: Number },
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }
      .card-header {
        display: flex;
        align-items: center;
        padding: 16px 16px 0;
        font-size: 1.1em;
        font-weight: 500;
        color: var(--primary-text-color);
      }
      .card-header ha-icon {
        margin-right: 8px;
        color: var(--primary-color);
      }
      .preview-container {
        padding: 16px;
        text-align: center;
      }
      .preview-container img {
        max-width: 100%;
        image-rendering: pixelated;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
      }
      .placeholder {
        padding: 32px;
        text-align: center;
        color: var(--secondary-text-color);
        font-style: italic;
      }
      .controls {
        padding: 0 16px 16px;
      }
      .controls label {
        display: block;
        font-size: 0.9em;
        font-weight: 500;
        margin-bottom: 4px;
        color: var(--primary-text-color);
      }
      textarea {
        width: 100%;
        box-sizing: border-box;
        font-family: monospace;
        font-size: 13px;
        line-height: 1.4;
        padding: 8px;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        background: var(--secondary-background-color, #f5f5f5);
        color: var(--secondary-text-color, #333);
        resize: vertical;
      }
      .dropdowns {
        display: flex;
        gap: 16px;
        margin-top: 12px;
      }
      .dropdown-group {
        flex: 1;
      }
      .dropdown-group label {
        font-size: 0.85em;
        margin-bottom: 2px;
      }
      .dropdown-group select {
        width: 100%;
        padding: 6px 8px;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        background: var(--secondary-background-color, #f5f5f5);
        color: var(--secondary-text-color, #333);
        font-size: 0.9em;
      }
      .buttons {
        display: flex;
        gap: 8px;
        margin-top: 16px;
      }
      .btn {
        flex: 1;
        padding: 8px 16px;
        border: none;
        border-radius: 4px;
        font-size: 0.9em;
        cursor: pointer;
        transition: opacity 0.2s;
      }
      .btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .btn-preview {
        background: transparent;
        border: 1px solid var(--primary-color);
        color: var(--primary-color);
      }
      .btn-send {
        background: var(--primary-color);
        color: var(--text-primary-color, #fff);
      }
      .status {
        margin-top: 8px;
        font-size: 0.8em;
        min-height: 1.2em;
      }
      .status.success {
        color: var(--success-color, #4caf50);
      }
      .status.error {
        color: var(--error-color, #db4437);
      }
    `;
  }

  constructor() {
    super();
    this._payloadText = "[]";
    this._sending = false;
    this._error = null;
    this._lastSent = null;
    this._background = "white";
    this._rotation = 0;
    this._cacheBuster = 0;
  }

  setConfig(config) {
    this._config = config;
    if (config.payload) {
      try {
        this._payloadText = JSON.stringify(config.payload, null, 2);
      } catch (_) {
        this._payloadText = "[]";
      }
    }
    if (config.background) this._background = config.background;
    if (config.rotate != null) this._rotation = config.rotate;
  }

  static getConfigElement() {
    import("./wolink-esl-card-editor.js");
    return document.createElement("wolink-esl-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "",
      payload: [{ type: "text", value: "Hello", x: 10, y: 10, size: 32 }],
      background: "white",
      rotate: 0,
    };
  }

  getCardSize() {
    return 5;
  }

  render() {
    if (!this._config || !this.hass) {
      return html`<ha-card><div class="placeholder">Loading...</div></ha-card>`;
    }

    const entityId = this._config.entity;
    if (!entityId) {
      return html`<ha-card><div class="placeholder">Select an entity (image.wolink_esl_*)</div></ha-card>`;
    }
    const stateObj = this.hass.states[entityId];
    const entityPicture = stateObj?.attributes?.entity_picture;

    const imgSrc = entityPicture
      ? `${entityPicture}${entityPicture.includes("?") ? "&" : "?"}t=${this._cacheBuster}`
      : null;

    const entityName =
      stateObj?.attributes?.friendly_name || entityId || "Wolink ESL";

    return html`
      <ha-card>
        <div class="card-header">
          <ha-icon icon="mdi:label-outline"></ha-icon>
          ${entityName}
        </div>

        <div class="preview-container">
          ${imgSrc
            ? html`<img src="${imgSrc}" alt="ESL preview" />`
            : html`<div class="placeholder">No preview available</div>`}
        </div>

        <div class="controls">
          <label>Payload:</label>
          <textarea
            rows="12"
            .value="${this._payloadText}"
            @input="${this._onPayloadInput}"
          ></textarea>

          <div class="dropdowns">
            <div class="dropdown-group">
              <label>Background:</label>
              <select
                .value="${this._background}"
                @change="${this._onBackgroundChange}"
              >
                <option value="white">White</option>
                <option value="black">Black</option>
                <option value="red">Red</option>
                <option value="yellow">Yellow</option>
              </select>
            </div>
            <div class="dropdown-group">
              <label>Rotation:</label>
              <select
                .value="${String(this._rotation)}"
                @change="${this._onRotationChange}"
              >
                <option value="0">0°</option>
                <option value="90">90°</option>
                <option value="180">180°</option>
                <option value="270">270°</option>
              </select>
            </div>
          </div>

          <div class="buttons">
            <button
              class="btn btn-preview"
              ?disabled="${this._sending}"
              @click="${this._onPreview}"
            >
              ${this._sending ? "Working..." : "Preview"}
            </button>
            <button
              class="btn btn-send"
              ?disabled="${this._sending}"
              @click="${this._onSend}"
            >
              ${this._sending ? "Working..." : "Send"}
            </button>
          </div>

          <div
            class="status ${this._error ? "error" : this._lastSent ? "success" : ""}"
          >
            ${this._error
              ? this._error
              : this._lastSent
                ? `Last sent: ${this._lastSent}`
                : ""}
          </div>
        </div>
      </ha-card>
    `;
  }

  _onPayloadInput(e) {
    this._payloadText = e.target.value;
  }

  _onBackgroundChange(e) {
    this._background = e.target.value;
  }

  _onRotationChange(e) {
    this._rotation = parseInt(e.target.value, 10);
  }

  async _callService(dryRun) {
    this._error = null;
    let payload;
    try {
      payload = JSON.parse(this._payloadText);
    } catch (err) {
      this._error = `JSON parse error: ${err.message}`;
      return;
    }

    if (!Array.isArray(payload)) {
      this._error = "Payload must be a JSON array";
      return;
    }

    this._sending = true;
    try {
      await this.hass.callService("wolink_esl", "drawcustom", {
        entity_id: this._config.entity,
        payload,
        background: this._background,
        rotate: this._rotation,
        dry_run: dryRun,
      });

      if (dryRun) {
        // Wait for HA to update the image entity, then refresh
        await new Promise((r) => setTimeout(r, 500));
        this._cacheBuster = Date.now();
      } else {
        this._lastSent = new Date().toLocaleTimeString();
        await new Promise((r) => setTimeout(r, 500));
        this._cacheBuster = Date.now();
      }
    } catch (err) {
      this._error = `Service call failed: ${err.message || err}`;
    } finally {
      this._sending = false;
    }
  }

  _onPreview() {
    this._callService(true);
  }

  _onSend() {
    this._callService(false);
  }
}

customElements.define("wolink-esl-card", WolinkEslCard);

// Register with HA card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: "wolink-esl-card",
  name: "Wolink ESL Display",
  description: "Preview and control Wolink BLE e-paper labels",
  preview: true,
});
