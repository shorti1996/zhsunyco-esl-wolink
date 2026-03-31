// Wolink ESL Card — Visual config editor for Lovelace UI
import { LitElement, html, css } from "lit";

class WolinkEslCardEditor extends LitElement {
  static get properties() {
    return {
      hass: { type: Object },
      _config: { type: Object },
    };
  }

  static get styles() {
    return css`
      :host {
        display: block;
      }
      .editor {
        padding: 16px;
      }
      .field {
        margin-bottom: 16px;
      }
      .field label {
        display: block;
        font-size: 0.85em;
        font-weight: 500;
        margin-bottom: 4px;
        color: var(--primary-text-color);
      }
      .field select,
      .field textarea {
        width: 100%;
        box-sizing: border-box;
        padding: 8px;
        border: 1px solid var(--divider-color);
        border-radius: 4px;
        background: var(--secondary-background-color, #f5f5f5);
        color: var(--secondary-text-color, #333);
        font-size: 0.9em;
      }
      .field textarea {
        font-family: monospace;
        font-size: 13px;
        resize: vertical;
      }
    `;
  }

  setConfig(config) {
    this._config = { ...config };
  }

  render() {
    if (!this._config) {
      return html``;
    }

    const payloadStr = this._config.payload
      ? JSON.stringify(this._config.payload, null, 2)
      : "[]";

    return html`
      <div class="editor">
        <div class="field">
          <label>Entity:</label>
          <ha-entity-picker
            .hass="${this.hass}"
            .value="${this._config.entity || ""}"
            .includeDomains="${["image"]}"
            allow-custom-entity
            @value-changed="${this._entityChanged}"
          ></ha-entity-picker>
        </div>

        <div class="field">
          <label>Background:</label>
          <select
            .value="${this._config.background || "white"}"
            @change="${this._backgroundChanged}"
          >
            <option value="white">White</option>
            <option value="black">Black</option>
            <option value="red">Red</option>
            <option value="yellow">Yellow</option>
          </select>
        </div>

        <div class="field">
          <label>Rotation:</label>
          <select
            .value="${String(this._config.rotate || 0)}"
            @change="${this._rotationChanged}"
          >
            <option value="0">0°</option>
            <option value="90">90°</option>
            <option value="180">180°</option>
            <option value="270">270°</option>
          </select>
        </div>

        <div class="field">
          <label>Payload (JSON):</label>
          <textarea rows="10" .value="${payloadStr}" @input="${this._payloadChanged}"></textarea>
        </div>
      </div>
    `;
  }

  _entityChanged(e) {
    const newConfig = { ...this._config, entity: e.detail.value };
    this._config = newConfig;
    this._fireChanged(newConfig);
  }

  _backgroundChanged(e) {
    const newConfig = { ...this._config, background: e.target.value };
    this._config = newConfig;
    this._fireChanged(newConfig);
  }

  _rotationChanged(e) {
    const newConfig = { ...this._config, rotate: parseInt(e.target.value, 10) };
    this._config = newConfig;
    this._fireChanged(newConfig);
  }

  _payloadChanged(e) {
    try {
      const payload = JSON.parse(e.target.value);
      const newConfig = { ...this._config, payload };
      this._config = newConfig;
      this._fireChanged(newConfig);
    } catch (_) {
      // Don't fire config-changed for invalid JSON
    }
  }

  _fireChanged(config) {
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config },
        bubbles: true,
        composed: true,
      })
    );
  }
}

customElements.define("wolink-esl-card-editor", WolinkEslCardEditor);
