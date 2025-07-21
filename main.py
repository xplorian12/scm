import json
import os
import re
import base64
import tempfile
from dash import Dash, dcc, html, Input, Output, State
from deepdiff import DeepDiff
from dash.dependencies import ALL
from dash import no_update
import dash
from flask import Flask

# === Initialize Dash App ===
server = Flask(__name__)
app = Dash(__name__, server=server)
app.title = "SCM Globe JSON Comparator"

# === Global State for Mappings and Results ===
FACILITY_NAMES_BY_ID = {}
FACILITY_NAMES_BY_INDEX = []
VEHICLE_NAMES_BY_PATH = {}
GEO_TO_FACILITY = {}
PRODUCT_NAMES_BY_ID = {}
base_data = {}
comparison_results = {}

# === Utility functions ===
def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def is_ignored_path(path):
    return bool(re.search(r"\['[^]]*id[^]]*'\]", path, re.IGNORECASE))

def rounded_geo(geo):
    try:
        return (round(float(geo[0]), 4), round(float(geo[1]), 4))
    except:
        return None

def get_facility_name_by_index(index):
    try:
        return FACILITY_NAMES_BY_INDEX[index]
    except:
        return f"Facility #{index + 1}"

def get_facility_name_by_id(fid):
    return FACILITY_NAMES_BY_ID.get(str(fid), f"Facility ID {fid}")

def get_facility_name_by_geo(geo):
    rgeo = rounded_geo(geo)
    return GEO_TO_FACILITY.get(rgeo, f"(Unknown Facility @ {geo})")

def get_vehicle_name_by_fac_index(fac_index, veh_index):
    return VEHICLE_NAMES_BY_PATH.get((fac_index, veh_index), f"Vehicle ({fac_index},{veh_index})")

# === Describes value changes (edits) ===
def describe_change(path, change):
    from_val = change.get('old_value')
    to_val = change.get('new_value')

    # Detect indices for context
    facility_match = re.search(r"\['facilities'\]\[(\d+)\]", path)
    vehicle_match = re.search(r"\['vehicles'\]\[(\d+)\]", path)
    product_match = re.search(r"\['products'\]\[(\d+)\]", path)
    stop_match = re.search(r"\['stops'\]\[(\d+)\]", path)

    facility_index = int(facility_match.group(1)) if facility_match else None
    vehicle_index = int(vehicle_match.group(1)) if vehicle_match else None
    product_index = int(product_match.group(1)) if product_match else None
    stop_index = int(stop_match.group(1)) + 1 if stop_match else "?"

    # Lookup human-friendly names
    facility_name = get_facility_name_by_index(facility_index) if facility_index is not None else "Unknown Facility"
    vehicle_name = get_vehicle_name_by_fac_index(facility_index, vehicle_index) if None not in (facility_index, vehicle_index) else "Unknown Vehicle"
    
    # === Prevent false positives for vehicle name changes due to removals ===
    if vehicle_match and path.endswith("['attrs']['name']"):
        return None  # Skip vehicle name changes entirely
    # Look up product ID and name
    product_id = None
    if product_index is not None:
        for dataset in [base_data.get("products", []), test_data.get("products", [])]:
            if product_index < len(dataset):
                product_id = dataset[product_index].get("attrs", {}).get("id")
                if product_id:
                    break

    product_name = PRODUCT_NAMES_BY_ID.get(str(product_id), f"Product #{product_index + 1}" if product_index is not None else "Unknown Product")

    # === Specific change types grouped by entity ===
    # Product changes
    if product_id and path.endswith("['attrs']['name']"):
        return f"{describe_change.counter}. Product name changed for {product_name}:\n   - From: \"{from_val}\"\n   - To:   \"{to_val}\""
    if product_id and path.endswith("['attrs']['price']"):
        return f"{describe_change.counter}. Product cost changed for {product_name}:\n   - From: {from_val}\n   - To:   {to_val}"
    if product_id and path.endswith("['attrs']['weight']"):
        return f"{describe_change.counter}. Product weight changed for {product_name}:\n   - From: {from_val}\n   - To:   {to_val}"
    if product_id and path.endswith("['attrs']['cube_size']"):
        return f"{describe_change.counter}. Product size changed for {product_name}:\n   - From: {from_val}\n   - To:   {to_val}"

    # Facility changes
    if "['storage_capacity']" in path:
        return f"{describe_change.counter}. Storage capacity changed at '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"
    if "['outputs']" in path:
        return f"{describe_change.counter}. Output quantity changed at facility item in '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"
    if "['demands']" in path:
        return f"{describe_change.counter}. Demand quantity changed at facility item in '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"
    if "['daily_carbon_output_kg']" in path:
        return f"{describe_change.counter}. Carbon Output quantity changed at facility item in '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"
    if "['stored']" in path:
        return f"{describe_change.counter}. Quantity on Hand changed at facility item in '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"
    if "['rent_cost']" in path:
        return f"{describe_change.counter}. Daily Rent Cost changed at facility item in '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"
    if "['opt_cost']" in path:
        return f"{describe_change.counter}. Daily Operating Cost changed at facility item in '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"
    if facility_match and path.endswith("['attrs']['name']") and path.startswith("root['facilities']") and "['vehicles']" not in path:
        return f"{describe_change.counter}. Facility Name changed at facility item in '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"

    # Vehicle changes
    if "['delay']" in path:
        return f"{describe_change.counter}. Vehicle delay changed for '{vehicle_name}' at '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"
    if vehicle_match and path.endswith("['attrs']['carry_volume']"):
        return f"{describe_change.counter}. Vehicle carry volume changed for '{vehicle_name}' at '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"
    if vehicle_match and path.endswith("['attrs']['speed']"):
        return f"{describe_change.counter}. Vehicle speed changed for '{vehicle_name}' at '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"
    if vehicle_match and path.endswith("['attrs']['cost_per_km']"):
        return f"{describe_change.counter}. Vehicle cost per km changed for '{vehicle_name}' at '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"
    if vehicle_match and path.endswith("['attrs']['max_weight']"):
        return f"{describe_change.counter}. Vehicle max weight changed for '{vehicle_name}' at '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"
    if vehicle_match and path.endswith("['attrs']['carbon_kg_per_km']"):
        return f"{describe_change.counter}. Vehicle carbon emissions per km changed for '{vehicle_name}' at '{facility_name}':\n   - From: {from_val}\n   - To:   {to_val}"


    # Route / Stop changes
    if "['geopath']" in path:
        return f"{describe_change.counter}. Route path (geopath) changed for {vehicle_name} at '{facility_name}':\n   - (Old and new paths differ; string too long to display.)"
    if path.endswith("['attrs']['distance']") and stop_match:
        return f"{describe_change.counter}. Stop distance changed at stop #{stop_index} ({vehicle_name}, Facility '{facility_name}'):\n   - From: {from_val} meters\n   - To:   {to_val} meters"
    if path.endswith("['attrs']['drop_vol']"):
        return f"{describe_change.counter}. Drop volume changed at stop #{stop_index} ({vehicle_name}, Facility '{facility_name}'):\n   - From: {from_val}\n   - To:   {to_val}"
    if path.endswith("['attrs']['distance']") and not stop_match:
        return f"{describe_change.counter}. Route distance changed (Facility '{facility_name}' → {vehicle_name}):\n   - From: {from_val} meters\n   - To:   {to_val}"

    if path == "root['attrs']['name']":
        return f"{describe_change.counter}. Scenario name changed:\n   - From: \"{from_val}\"\n   - To:   \"{to_val}\""
        

    return f"{describe_change.counter}. Change at {path}:\n   - From: {from_val}\n   - To:   {to_val}"

# === Describes item additions/removals (not just changes) ===
def describe_add_remove(path, value, is_addition):
    stop_match = re.search(r"\['stops'\]\[(\d+)\]", path)
    vehicle_match = re.search(r"\['vehicles'\]\[(\d+)\]", path)
    facility_match = re.search(r"\['facilities'\]\[(\d+)\]", path)
    vehicle_index = int(vehicle_match.group(1)) if vehicle_match else None
    facility_index = int(facility_match.group(1)) if facility_match else None
    vehicle_name = get_vehicle_name_by_fac_index(facility_index, vehicle_index) if None not in (facility_index, vehicle_index) else "Unknown Vehicle"

    # Detect facility add/remove
    if "['facilities']" in path and "['attrs']" in path and isinstance(value, dict) and 'name' in value:
        name = value.get('name', '(Unnamed Facility)')
        return f"{describe_add_remove.counter + 1}. Facility {'added' if is_addition else 'removed'}: \"{name}\""
    
    # Detect vehicle add/remove
    if re.match(r"root\['facilities'\]\[\d+\]\['vehicles'\]\[\d+\]$", path) and isinstance(value, dict):
        name = value.get('attrs', {}).get('name', '(Unnamed Vehicle)')
        return f"{describe_add_remove.counter + 1}. Vehicle {'added' if is_addition else 'removed'}: \"{name}\""


    # Detect stop changes
    if stop_match and isinstance(value, dict):
        geo = value.get('geo')
        end_fac_id = value.get('attrs', {}).get('end_facility_id')
        if geo:
            dest_name = get_facility_name_by_geo(geo)
        elif end_fac_id:
            dest_name = FACILITY_NAMES_BY_ID.get(str(end_fac_id), f"Facility ID {end_fac_id}")
        else:
            dest_name = "(Unknown Destination)"
        return f"{describe_add_remove.counter + 1}. Stop {'added to' if is_addition else 'removed from'} route ({vehicle_name}):\n   - Destination: '{dest_name}'"
    return None

# === Prepare dictionaries for mapping IDs and paths to readable names ===
def _prepare_mappings(base_data, test_data):
    global FACILITY_NAMES_BY_ID, FACILITY_NAMES_BY_INDEX, VEHICLE_NAMES_BY_PATH, GEO_TO_FACILITY, PRODUCT_NAMES_BY_ID
    FACILITY_NAMES_BY_ID, VEHICLE_NAMES_BY_PATH, GEO_TO_FACILITY, PRODUCT_NAMES_BY_ID = {}, {}, {}, {}

    # Map product ID → name
    for p in base_data.get("products", []) + test_data.get("products", []):
        pid = p.get("attrs", {}).get("id")
        name = p.get("attrs", {}).get("name")
        if pid and name:
            PRODUCT_NAMES_BY_ID[str(pid)] = name

    # Map facility ID → name, and geo → name
    for f in base_data.get("facilities", []) + test_data.get("facilities", []):
        name = f.get("attrs", {}).get("name", "(Unnamed)")
        if 'id' in f and 'attrs' in f:
            FACILITY_NAMES_BY_ID[str(f['id'])] = name
        try:
            lat, lon = float(f["attrs"]["lat"]), float(f["attrs"]["lon"])
            GEO_TO_FACILITY[rounded_geo([lat, lon])] = name
        except:
            pass

    FACILITY_NAMES_BY_INDEX = [f.get("attrs", {}).get("name", "(Unnamed)") for f in base_data.get("facilities", [])]
    for f_idx, fac in enumerate(base_data.get("facilities", [])):
        for v_idx, v in enumerate(fac.get("vehicles", [])):
            VEHICLE_NAMES_BY_PATH[(f_idx, v_idx)] = v["attrs"].get("name", f"Vehicle #{v_idx + 1}")

# === Check that files share a facility, otherwise don't compare ===
def shared_facilities_exist(base_data, test_data):
    base_names = set(f.get("attrs", {}).get("name") for f in base_data.get("facilities", []))
    test_names = set(f.get("attrs", {}).get("name") for f in test_data.get("facilities", []))
    return bool(base_names & test_names)  # intersection not empty

# === LAYOUT: UI elements for file upload, selection, and results display ===
app.layout = html.Div([
    html.H2("📊 SCM Globe JSON Comparison Tool", style={'textAlign': 'center', 'marginTop': '20px'}),
    html.Div([
        dcc.Dropdown(
            id='base-dropdown',
            options=[{'label': f, 'value': f} for f in os.listdir('base_cases') if f.endswith('.json')],
            placeholder="Select a base case JSON file",
            style={'marginBottom': '15px'}
        ),
        dcc.Upload(
            id='upload-testfiles',
            children=html.Div(['📂 Drag & drop multiple test JSON files here']),
            multiple=True,
            style={
                'width': '100%',
                'height': '80px',
                'lineHeight': '80px',
                'borderWidth': '1px',
                'borderStyle': 'dashed',
                'borderRadius': '8px',
                'textAlign': 'center',
                'marginBottom': '10px',
                'backgroundColor': '#f9f9f9'
            }
        ),
        html.Div(id='file-list', style={'margin': '10px 0', 'fontSize': '14px'}),
        html.Button("🔍 Compare Files", id="compare-button", n_clicks=0, style={'marginBottom': '15px'}),
        dcc.Store(id='stored-testfiles', data={"filenames": [], "contents": []}),
        dcc.Dropdown(id="testfile-dropdown", placeholder="Select a test file to view comparison", style={'marginBottom': '20px'}),
        html.Div([
            html.Pre(id='results', style={
                'whiteSpace': 'pre-wrap',
                'padding': '15px',
                'border': '1px solid #ddd',
                'borderRadius': '8px',
                'backgroundColor': '#fafafa',
                'maxHeight': '600px',
                'overflowY': 'auto'
            })
        ])
    ], style={'maxWidth': '800px', 'margin': '0 auto'})
])

# === CALLBACK: Handle file uploads and removals ===
@app.callback(
    Output("file-list", "children"),
    Output("stored-testfiles", "data"),
    Input("upload-testfiles", "contents"),
    State("upload-testfiles", "filename"),
    Input({'type': 'remove-btn', 'index': ALL}, 'n_clicks'),
    State("stored-testfiles", "data"),
    prevent_initial_call=True
)

def update_files(upload_contents, upload_filenames, remove_clicks, stored_data):
    ctx = dash.callback_context

    # Start from stored values
    filenames = stored_data["filenames"]
    contents = stored_data["contents"]

    # Determine what triggered the callback
    if ctx.triggered and "upload-testfiles" in ctx.triggered[0]["prop_id"]:
        if not upload_contents:
            return no_update, no_update
        filenames += upload_filenames
        contents += upload_contents

    elif ctx.triggered and "remove-btn" in ctx.triggered[0]["prop_id"]:
        triggered_idx = [i for i, n in enumerate(remove_clicks) if n > 0]
        if triggered_idx:
            idx = triggered_idx[0]
            if idx < len(filenames):
                filenames.pop(idx)
                contents.pop(idx)

    if not filenames:
        return "No test files uploaded yet.", {"filenames": [], "contents": []}

    file_list = html.Div([
        html.Strong("Test files uploaded:"),
        html.Ul([
            html.Li([
                f"📄 {name} ",
                html.Button("❌ Remove", id={'type': 'remove-btn', 'index': i}, n_clicks=0, style={'marginLeft': '10px'})
            ]) for i, name in enumerate(filenames)
        ])
    ])

    return file_list, {"filenames": filenames, "contents": contents}

# === CALLBACK: Run comparisons on all uploaded files ===
def show_uploaded_files(filenames):
    if not filenames:
        return "No test files uploaded yet."
    return html.Div([
        html.Strong("Test files uploaded:"),
        html.Ul([html.Li(f"📄 {f}") for f in filenames])
    ])

@app.callback(
    Output("testfile-dropdown", "options"),
    Output("testfile-dropdown", "value"),
    Input("compare-button", "n_clicks"),
    State("base-dropdown", "value"),
    State("stored-testfiles", "data"),
)


def compare_multiple_files(n_clicks, base_file, stored_testfiles):
    uploaded_filenames = stored_testfiles["filenames"]
    uploaded_contents = stored_testfiles["contents"]
    global comparison_results, base_data, test_data
    if not n_clicks or not base_file or not uploaded_contents:
        return [], None

    comparison_results = {}
    base_data = load_json(os.path.join("base_cases", base_file))

    for content, fname in zip(uploaded_contents, uploaded_filenames):
        content_type, content_string = content.split(',')
        decoded = base64.b64decode(content_string)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode='wb') as tmp:
            tmp.write(decoded)
            tmp_path = tmp.name
        test_data = load_json(tmp_path)

        _prepare_mappings(base_data, test_data)

        if not shared_facilities_exist(base_data, test_data):
            comparison_results[
                fname] = "⚠️ No shared facility names between base and test file. Likely wrong model — comparison skipped."
            continue

        diff = DeepDiff(base_data, test_data, verbose_level=2)
        lines = []
        describe_change.counter = 1
        for path, change in diff.get('values_changed', {}).items():
            if not is_ignored_path(path):
                lines.append(describe_change(path, change))
                describe_change.counter += 1

        describe_add_remove.counter = describe_change.counter - 1
        for path, value in diff.get('iterable_item_added', {}).items():
            desc = describe_add_remove(path, value, is_addition=True)
            if desc:
                lines.append(desc)
                describe_add_remove.counter += 1
        for path, value in diff.get('iterable_item_removed', {}).items():
            desc = describe_add_remove(path, value, is_addition=False)
            if desc:
                lines.append(desc)
                describe_add_remove.counter += 1

        result = "\n\n".join([str(l) for l in lines if l]) if lines else "✅ Only differences in ignored fields. No meaningful changes."
        comparison_results[fname] = result

    return [{'label': f, 'value': f} for f in uploaded_filenames], uploaded_filenames[0]

# === CALLBACK: Show comparison results for selected file ===
@app.callback(
    Output("results", "children"),
    Input("testfile-dropdown", "value")
)


def show_selected_result(selected_file):
    return comparison_results.get(selected_file, "") if selected_file else ""

# === Run App ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
