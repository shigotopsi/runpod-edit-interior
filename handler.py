# ============================================================================
# This is a MERGED handler file.
# It combines the robust default handler from the runpod/worker-comfyui image
# with your custom logic for preparing workflows and uploading to Cloudflare.
# ============================================================================

import requests
import runpod
import base64
import json
import urllib
import uuid
import os
import time
import websocket
import traceback
from io import BytesIO

# --- Environment Configuration (From Your Script) ---
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN")

# --- Default Handler Configuration ---
COMFY_HOST = "127.0.0.1:8188"

# ============================================================================
# --- START: YOUR CUSTOM HELPER FUNCTIONS ---
# These functions are the core of your custom logic.
# ============================================================================

WORKFLOW_DEFAULTS = {
    "interior_redesign": {
        "_CONTROLNET_STRENGTH_": 0.6,
        "_CONTROLNET_END_PERCENT_": 0.6,
        "_SEED_": 1,
        "_STEPS_": 20,
        "_GUIDANCE_": 3.5,
        "_SAMPLER_NAME_": "euler",
        "_SCHEDULER_": "beta",
        "_DENOISE_": 1.0,
    },
    "virtual_staging": {
        "_SEED_": 1,
        "_STEPS_": 20,
        "_GUIDANCE_": 3.0,
        "_SAMPLER_NAME_": "euler",
        "_SCHEDULER_": "beta",
        "_DENOISE_": 1.0,
    },
    "hires_fix": {
        "_HIRES_SCALE_BY_": 1.0,
        "_HIRES_SEED_": 1,
        "_HIRES_STEPS_": 20,
        "_HIRES_GUIDANCE_": 3.5,
        "_HIRES_SAMPLER_NAME_": "euler",
        "_HIRES_SCHEDULER_": "beta",
        "_HIRES_DENOISE_": 0.4,
    },
}


def _replace_placeholders(obj: any, replacements: dict) -> any:
    if isinstance(obj, dict):
        return {k: _replace_placeholders(v, replacements) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_replace_placeholders(elem, replacements) for elem in obj]
    elif isinstance(obj, str):
        return replacements.get(obj, obj)
    else:
        return obj


def _image_url_to_base64(image_url: str) -> str:
    response = requests.get(image_url)
    response.raise_for_status()
    # The default handler needs the data URI prefix.
    return f"data:image/png;base64,{base64.b64encode(response.content).decode('utf-8')}"


def prepare_comfy_input(job_input: dict) -> dict:
    """
    This is your core logic function. It takes the user-friendly input and
    builds the complex ComfyUI workflow and image list.
    """
    # 1. Validate and Extract primary information
    required_fields = ["workflow", "room", "style", "image_url"]
    for field in required_fields:
        if field not in job_input:
            raise ValueError(f"Missing required field in input: '{field}'")

    workflow_name = job_input["workflow"]
    room = job_input["room"]
    style = job_input["style"]
    parameters = job_input.get("parameters", {})
    mask_enabled = parameters.get("mask", {}).get("enabled", False)
    hires_enabled = parameters.get("hires", {}).get("enabled", False)

    # 2. Determine which workflow file to load
    base_version = parameters.get("version", "1.0.0")
    hires_version = parameters.get("hires", {}).get("version", "1.0.0")

    file_name = (
        f"hires_v{hires_version}.json"
        if hires_enabled
        else f"base_v{base_version}.json"
    )

    workflow_path = ""
    if mask_enabled:
        mask_type = parameters.get("mask", {}).get("type")
        if not mask_type:
            raise ValueError("Mask is enabled but 'type' is missing.")
        workflow_path = os.path.join(
            "workflows", workflow_name, "mask", mask_type, file_name
        )
    else:
        workflow_path = os.path.join("workflows", workflow_name, file_name)

    with open(workflow_path, "r") as f:
        template = json.load(f)

    # 3. Load prompts
    prompt_file = f"{room}.json"
    prompt_path = os.path.join("prompts", workflow_name, prompt_file)
    with open(prompt_path, "r") as f:
        prompts = json.load(f)

    base_prompt = prompts[style]["base_prompt"]
    hires_prompt = ""
    if hires_enabled:
        hires_prompt = prompts[style]["hires_prompt"]

    # 4. Create placeholder replacement map
    replacement_map = WORKFLOW_DEFAULTS[workflow_name].copy()
    if hires_enabled:
        replacement_map.update(WORKFLOW_DEFAULTS["hires_fix"])

    for key, value in parameters.items():
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                placeholder = f"_{key.upper()}_{nested_key.upper()}_"
                if placeholder in replacement_map:
                    replacement_map[placeholder] = nested_value
        else:
            placeholder = f"_{key.upper()}_"
            if placeholder in replacement_map:
                replacement_map[placeholder] = value

    image_id = uuid.uuid4().hex
    mask_id = uuid.uuid4().hex
    replacement_map.update(
        {
            "_BASE_PROMPT_": base_prompt,
            "_HIRES_PROMPT_": hires_prompt,
            "_IMAGE_": f"{image_id}.png",
        }
    )

    if mask_enabled:
        mask_type = parameters.get("mask", {}).get("type")
        mask_value = parameters.get("mask", {}).get("value")
        if not (mask_type and mask_value):
            raise ValueError("Mask is enabled but 'type' or 'value' is missing.")

        if mask_type == "prompt":
            replacement_map["_MASK_PROMPT_"] = mask_value
        elif mask_type == "url":
            replacement_map["_MASK_"] = f"{mask_id}.png"

    # 5. Process template and prepare images
    final_workflow = _replace_placeholders(template, replacement_map)
    images_to_upload = []

    images_to_upload.append(
        {
            "name": f"{image_id}.png",
            "image": _image_url_to_base64(job_input["image_url"]),
        }
    )

    if mask_enabled and parameters.get("mask", {}).get("type") == "url":
        mask_url = parameters.get("mask", {}).get("value")
        images_to_upload.append(
            {"name": f"{mask_id}.png", "image": _image_url_to_base64(mask_url)}
        )

    # Return the final structure expected by the default handler
    return {"workflow": final_workflow, "images": images_to_upload}


def upload_to_cloudflare(image_bytes: bytes) -> str:
    """
    Uploads image bytes to Cloudflare and returns the public URL.
    """
    unique_id = uuid.uuid4().hex
    api_url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/images/v1"
    headers = {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"}
    files = {"file": (f"{unique_id}.png", image_bytes, "image/png")}

    response = requests.post(api_url, headers=headers, files=files)
    response.raise_for_status()

    upload_result = response.json()
    variants = upload_result.get("result", {}).get("variants")
    if not variants:
        raise ValueError(
            f"Cloudflare response is missing image variants: {upload_result}"
        )

    return variants[0]


# ============================================================================
# --- END: YOUR CUSTOM HELPER FUNCTIONS ---
# ============================================================================


def get_image(filename, subfolder, folder_type):
    # This is a helper from the default handler
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen(f"http://{COMFY_HOST}/view?{url_values}") as response:
        return response.read()


def queue_prompt(prompt, client_id):
    # This is a helper from the default handler
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode("utf-8")
    req = urllib.request.Request(f"http://{COMFY_HOST}/prompt", data=data)
    return json.loads(urllib.request.urlopen(req).read())


def get_history(prompt_id):
    # This is a helper from the default handler
    with urllib.request.urlopen(f"http://{COMFY_HOST}/history/{prompt_id}") as response:
        return json.loads(response.read())


def get_images(ws, prompt, client_id):
    # This is a helper from the default handler
    prompt_id = queue_prompt(prompt, client_id)["prompt_id"]
    output_images = {}

    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message["type"] == "executing":
                data = message["data"]
                if data["node"] is None and data["prompt_id"] == prompt_id:
                    break  # Execution is done
        else:
            continue  # previews are binary data

    history = get_history(prompt_id)[prompt_id]
    for node_id in history["outputs"]:
        node_output = history["outputs"][node_id]
        if "images" in node_output:
            images_output = []
            for image in node_output["images"]:
                image_data = get_image(
                    image["filename"], image["subfolder"], image["type"]
                )
                images_output.append(image_data)
            output_images[node_id] = images_output

    return output_images


# ============================================================================
# --- THE MAIN HANDLER ---
# This combines your logic with the default handler's execution flow.
# ============================================================================


def handler(job):
    job_input = job["input"]

    try:
        # --- YOUR LOGIC, PART 1: PREPARE THE WORKFLOW ---
        # Call your function to translate the simple input into a ComfyUI workflow
        comfy_input = prepare_comfy_input(job_input)

        comfy_workflow = comfy_input["workflow"]
        comfy_images_to_upload = comfy_input["images"]

        # --- DEFAULT HANDLER LOGIC: UPLOAD INPUT IMAGES ---
        # The default handler has logic to upload images to ComfyUI's /upload/image endpoint
        # We need to adapt it slightly.
        for image_to_upload in comfy_images_to_upload:
            name = image_to_upload["name"]
            image_data_uri = image_to_upload["image"]
            base64_data = image_data_uri.split(",", 1)[1]
            blob = base64.b64decode(base64_data)
            files = {
                "image": (name, BytesIO(blob), "image/png"),
                "overwrite": (None, "true"),
            }
            requests.post(
                f"http://{COMFY_HOST}/upload/image", files=files, timeout=30
            ).raise_for_status()

        # --- DEFAULT HANDLER LOGIC: EXECUTE AND GET OUTPUT IMAGE ---
        client_id = str(uuid.uuid4())
        ws = websocket.WebSocket()

        for _ in range(10):  # Wait for websocket to be available
            try:
                ws.connect(f"ws://{COMFY_HOST}/ws?clientId={client_id}", timeout=1)
                break
            except websocket.WebSocketException:
                time.sleep(1)
        else:
            raise ConnectionRefusedError("Could not connect to ComfyUI websocket")

        # This function queues the job and waits for the final image bytes
        images_output = get_images(ws, comfy_workflow, client_id)
        ws.close()

        # We assume the last node with images contains the final result
        final_image_bytes = None
        for node_id in images_output:
            for image_bytes in images_output[node_id]:
                final_image_bytes = image_bytes  # Grab the last image

        if not final_image_bytes:
            raise ValueError("Workflow did not produce an output image.")

        # --- YOUR LOGIC, PART 2: UPLOAD TO CLOUDFLARE ---
        # Now that we have the final image, call your Cloudflare function
        image_url = upload_to_cloudflare(final_image_bytes)

        return {"image_url": image_url}

    # --- DEFAULT HANDLER LOGIC: ERROR HANDLING ---
    except Exception as e:
        print(traceback.format_exc())
        return {"error": str(e)}


# Start the serverless worker
runpod.serverless.start({"handler": handler})
