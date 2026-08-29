from flask import Flask, jsonify, redirect, render_template_string, request
import json
import os
import threading

from bot_service import BotService

app = Flask(__name__)
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")
bot = BotService(SETTINGS_FILE)

HTML = """
<!doctype html>
<html lang="en">
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AutoC</title>
<style>
body{font-family:system-ui,sans-serif;background:#101318;color:#f4f5f7;margin:0;padding:16px}
main{max-width:760px;margin:auto}.card{background:#191e26;border:1px solid #303744;border-radius:16px;padding:16px;margin:12px 0}
h1{margin:4px 0}.muted{color:#9da7b5}.row{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:10px 0;border-bottom:1px solid #2b313c}
.row:last-child{border-bottom:0}button,select{font:inherit;border-radius:10px;padding:10px 14px;border:1px solid #46505f;background:#242b36;color:#fff}button{cursor:pointer}.primary{width:100%;margin-top:12px}
</style>
</head><body><main>
<h1>🤖 AutoC</h1><div class="muted">Smart automation control panel</div>
<div class="card"><div class="row"><span>Status</span><strong id="status">Loading…</strong></div><div class="row"><span>Strategy</span><select id="strategy"><option value="balanced">Balanced</option><option value="progression">Fast Progression</option><option value="conservative">Conservative</option></select></div></div>
<div class="card"><h3>Home Village</h3>
<div class="row"><span>Smart upgrades</span><input id="home_upgrades" type="checkbox"></div>
<div class="row"><span>Smart walls</span><input id="home_walls" type="checkbox"></div>
<div class="row"><span>Smart heroes</span><input id="home_heroes" type="checkbox"></div>
<div class="row"><span>Smart laboratory</span><input id="home_lab" type="checkbox"></div>
<div class="row"><span>Smart builders</span><input id="home_builders" type="checkbox"></div></div>
<div class="card"><h3>Builder Base</h3>
<div class="row"><span>Smart upgrades</span><input id="bb_upgrades" type="checkbox"></div>
<div class="row"><span>Smart walls</span><input id="bb_walls" type="checkbox"></div>
<div class="row"><span>Smart laboratory</span><input id="bb_lab" type="checkbox"></div></div>
<div class="card"><h3>Farming</h3><div class="row"><span>Smart farming</span><input id="farm" type="checkbox"></div>
<div class="row"><span>Max opponent skips</span><input id="skips" type="number" min="0" max="100" style="width:80px"></div></div>
<button class="primary" onclick="save()">Save settings</button><button class="primary" onclick="toggle()" id="toggle">Start bot</button>
<script>
async function load(){let r=await fetch('/api/settings');let s=await r.json();document.getElementById('strategy').value=s.strategy;set('home_upgrades',s.home_village.smart_upgrades);set('home_walls',s.home_village.smart_walls);set('home_heroes',s.home_village.smart_heroes);set('home_lab',s.home_village.smart_lab);set('home_builders',s.home_village.smart_builders);set('bb_upgrades',s.builder_base.smart_upgrades);set('bb_walls',s.builder_base.smart_walls);set('bb_lab',s.builder_base.smart_lab);set('farm',s.farming.enabled);document.getElementById('skips').value=s.farming.max_opponent_skips;status();}
function set(id,v){document.getElementById(id).checked=!!v}
async function save(){let s=await (await fetch('/api/settings')).json();s.strategy=document.getElementById('strategy').value;s.home_village.smart_upgrades=document.getElementById('home_upgrades').checked;s.home_village.smart_walls=document.getElementById('home_walls').checked;s.home_village.smart_heroes=document.getElementById('home_heroes').checked;s.home_village.smart_lab=document.getElementById('home_lab').checked;s.home_village.smart_builders=document.getElementById('home_builders').checked;s.builder_base.smart_upgrades=document.getElementById('bb_upgrades').checked;s.builder_base.smart_walls=document.getElementById('bb_walls').checked;s.builder_base.smart_lab=document.getElementById('bb_lab').checked;s.farming.enabled=document.getElementById('farm').checked;s.farming.max_opponent_skips=Math.max(0,Math.min(100,Number(document.getElementById('skips').value)||0));await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(s)});alert('Saved');}
async function toggle(){let r=await fetch('/api/toggle',{method:'POST'});let s=await r.json();document.getElementById('status').textContent=s.running?'Running':'Stopped';document.getElementById('toggle').textContent=s.running?'Stop bot':'Start bot'}
async function status(){let s=await (await fetch('/api/status')).json();document.getElementById('status').textContent=s.running?'Running':'Stopped';document.getElementById('toggle').textContent=s.running?'Stop bot':'Start bot'}
load();setInterval(status,3000);
</script></main></body></html>
"""

@app.get("/")
def index():
    return render_template_string(HTML)

@app.get("/api/settings")
def get_settings():
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))

@app.post("/api/settings")
def save_settings():
    data = request.get_json(force=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    bot.reload()
    return jsonify({"ok": True})

@app.get("/api/status")
def status():
    return jsonify({"running": bot.running})

@app.post("/api/toggle")
def toggle():
    bot.toggle()
    return jsonify({"running": bot.running})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
