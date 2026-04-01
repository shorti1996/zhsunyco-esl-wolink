import{i as e,a as t,b as i}from"./wolink-esl-card.js";class o extends e{static get properties(){return{hass:{type:Object},_config:{type:Object}}}static get styles(){return t`
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
    `}setConfig(e){this._config={...e}}render(){if(!this._config)return i``;const e=this._config.payload?JSON.stringify(this._config.payload,null,2):"[]";return i`
      <div class="editor">
        <div class="field">
          <label>Entity:</label>
          <ha-entity-picker
            .hass="${this.hass}"
            .value="${this._config.entity||""}"
            .includeDomains="${["image"]}"
            allow-custom-entity
            @value-changed="${this._entityChanged}"
          ></ha-entity-picker>
        </div>

        <div class="field">
          <label>Background:</label>
          <select
            .value="${this._config.background||"white"}"
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
            .value="${String(this._config.rotate||0)}"
            @change="${this._rotationChanged}"
          >
            <option value="0">0°</option>
            <option value="90">90°</option>
            <option value="180">180°</option>
            <option value="270">270°</option>
          </select>
        </div>

        <div class="field">
          <label>Mirror:</label>
          <select
            .value="${this._config.mirror||"none"}"
            @change="${this._mirrorChanged}"
          >
            <option value="none">None</option>
            <option value="horizontal">Horizontal</option>
            <option value="vertical">Vertical</option>
          </select>
        </div>

        <div class="field">
          <label>Payload (JSON):</label>
          <textarea rows="10" .value="${e}" @input="${this._payloadChanged}"></textarea>
        </div>
      </div>
    `}_entityChanged(e){const t={...this._config,entity:e.detail.value};this._config=t,this._fireChanged(t)}_backgroundChanged(e){const t={...this._config,background:e.target.value};this._config=t,this._fireChanged(t)}_rotationChanged(e){const t={...this._config,rotate:parseInt(e.target.value,10)};this._config=t,this._fireChanged(t)}_mirrorChanged(e){const t={...this._config,mirror:e.target.value};this._config=t,this._fireChanged(t)}_payloadChanged(e){try{const t=JSON.parse(e.target.value),i={...this._config,payload:t};this._config=i,this._fireChanged(i)}catch(e){}}_fireChanged(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}}customElements.get("wolink-esl-card-editor")||customElements.define("wolink-esl-card-editor",o);
