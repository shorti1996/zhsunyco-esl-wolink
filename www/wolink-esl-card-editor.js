import{i as e,a as t,b as a}from"./wolink-esl-card.js";const i=e=>e.map(e=>a`<mwc-list-item value=${e.value}>${e.label}</mwc-list-item>`),l=[{value:"white",label:"White"},{value:"black",label:"Black"},{value:"red",label:"Red"},{value:"yellow",label:"Yellow"}],o=[{value:"0",label:"0°"},{value:"90",label:"90°"},{value:"180",label:"180°"},{value:"270",label:"270°"}],n=[{value:"none",label:"None"},{value:"horizontal",label:"Horizontal"},{value:"vertical",label:"Vertical"}];class s extends e{static get properties(){return{hass:{type:Object},_config:{type:Object}}}static get styles(){return t`
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
      ha-select {
        width: 100%;
      }
      .field textarea {
        font-family: monospace;
        font-size: 13px;
        resize: vertical;
      }
    `}setConfig(e){this._config={...e}}render(){if(!this._config)return a``;const e=this._config.payload?JSON.stringify(this._config.payload,null,2):"[]";return a`
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
          <ha-select
            label="Background"
            .options=${l}
            .value=${this._config.background||"white"}
            @selected=${this._backgroundChanged}
            @closed=${e=>e.stopPropagation()}
          >
            ${i(l)}
          </ha-select>
        </div>

        <div class="field">
          <ha-select
            label="Rotation"
            .options=${o}
            .value=${String(this._config.rotate||0)}
            @selected=${this._rotationChanged}
            @closed=${e=>e.stopPropagation()}
          >
            ${i(o)}
          </ha-select>
        </div>

        <div class="field">
          <ha-select
            label="Mirror"
            .options=${n}
            .value=${this._config.mirror||"none"}
            @selected=${this._mirrorChanged}
            @closed=${e=>e.stopPropagation()}
          >
            ${i(n)}
          </ha-select>
        </div>

        <div class="field">
          <label>Payload (JSON):</label>
          <textarea rows="10" .value="${e}" @input="${this._payloadChanged}"></textarea>
        </div>
      </div>
    `}_entityChanged(e){const t={...this._config,entity:e.detail.value};this._config=t,this._fireChanged(t)}_backgroundChanged(e){const t=e.detail?.value??e.target?.value;if(!t)return;const a={...this._config,background:t};this._config=a,this._fireChanged(a)}_rotationChanged(e){const t=e.detail?.value??e.target?.value;if(null==t)return;const a={...this._config,rotate:parseInt(t,10)};this._config=a,this._fireChanged(a)}_mirrorChanged(e){const t=e.detail?.value??e.target?.value;if(!t)return;const a={...this._config,mirror:t};this._config=a,this._fireChanged(a)}_payloadChanged(e){try{const t=JSON.parse(e.target.value),a={...this._config,payload:t};this._config=a,this._fireChanged(a)}catch(e){}}_fireChanged(e){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:e},bubbles:!0,composed:!0}))}}customElements.get("wolink-esl-card-editor")||customElements.define("wolink-esl-card-editor",s);
