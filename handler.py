import requests
import runpod
import base64
import json
import uuid
import os

# --- Environment Configuration ---
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN")
RUNPOD_API_KEY = os.environ.get("RUNPOD_API_KEY")
ENDPOINT_ID = os.environ.get("ENDPOINT_ID")

# --- Initialize RunPod ---
runpod.api_key = RUNPOD_API_KEY
endpoint = runpod.Endpoint(ENDPOINT_ID)


# --- Default Workflow Parameters ---
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
    """
    Recursively traverses a dictionary or list, replacing placeholder strings
    with their corresponding values from the replacements map.
    """
    if isinstance(obj, dict):
        return {k: _replace_placeholders(v, replacements) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_replace_placeholders(elem, replacements) for elem in obj]
    elif isinstance(obj, str):
        return replacements.get(obj, obj)
    else:
        return obj


def _image_url_to_base64(image_url: str) -> str:
    """
    Downloads an image from the given URL and encodes it to a base64 string.
    """
    response = requests.get(image_url)
    response.raise_for_status()
    return base64.b64encode(response.content).decode("utf-8")


def prepare_runpod_input(job_input: dict) -> dict:
    """
    Transforms the user-facing job input into the format required by the RunPod endpoint.

    Args:
        job_input: A dictionary containing the user's request (image_url, workflow, room, style, etc.).
        unique_id: A unique identifier for this specific job run.

    Returns:
        A dictionary formatted for the RunPod /run or /runsync endpoint.
    """

    # 1. Extract primary information from the job input.
    workflow = job_input["workflow"]
    room = job_input["room"]
    style = job_input["style"]
    parameters = job_input.get("parameters", {})
    mask_enabled = parameters.get("mask", {}).get("enabled", False)
    hires_enabled = parameters.get("hires", {}).get("enabled", False)

    # 2. Determine which workflow file to load.
    base_version = parameters.get("version", "1.0.0")
    hires_version = parameters.get("hires", {}).get("version", "1.0.0")

    if hires_enabled:
        file = f"hires_v{hires_version}.json"
    else:
        file = f"base_v{base_version}.json"

    if mask_enabled:
        match parameters.get("mask", {}).get("type"):
            case "prompt":
                path = os.path.join("workflows", workflow, "mask", "prompt", file)
            case "url":
                path = os.path.join("workflows", workflow, "mask", "url", file)
            case _:
                raise ValueError(
                    f"Unknown mask type: {parameters.get('mask', {}).get('type')}"
                )
    else:
        path = os.path.join("workflows", workflow, file)

    with open(path, "r") as f:
        template = json.load(f)

    # 3. Load the prompt based on the requested room and style.
    file = f"{room}.json"
    path = os.path.join("prompts", workflow, file)

    with open(path, "r") as f:
        prompts = json.load(f)

    base_prompt = prompts[style]["base_prompt"]
    hires_prompt = ""

    if hires_enabled:
        hires_prompt = prompts[style]["hires_prompt"]

    # 4. Create the placeholder replacement map using defined defaults.
    replacement_map = WORKFLOW_DEFAULTS[workflow].copy()

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

    replacement_map["_BASE_PROMPT_"] = base_prompt
    replacement_map["_HIRES_PROMPT_"] = hires_prompt
    replacement_map["_IMAGE_"] = f"{image_id}.png"

    if mask_enabled:
        mask_params = parameters.get("mask", {})
        mask_type = mask_params.get("type")
        mask_value = mask_params.get("value")

        if mask_type and mask_value:
            match mask_type:
                case "prompt":
                    replacement_map["_MASK_PROMPT_"] = mask_value
                case "url":
                    replacement_map["_MASK_"] = f"{mask_id}.png"
                case _:
                    raise ValueError(f"Unknown mask type: {mask_type}")
        else:
            raise ValueError("Mask is enabled but 'type' or 'value' is missing.")

    # 5. Process the template and images
    workflow = _replace_placeholders(template, replacement_map)
    images = []

    base64_image = _image_url_to_base64(job_input["image_url"])
    images.append({"name": f"{image_id}.png", "image": base64_image})

    if mask_enabled and parameters.get("mask", {}).get("type") == "url":
        mask_url = parameters.get("mask", {}).get("value")
        base64_mask = _image_url_to_base64(mask_url)
        images.append({"name": f"{mask_id}.png", "image": base64_mask})

    # 6. Assemble the final RunPod input dictionary
    runpod_input = {
        "workflow": workflow,
        "images": images,
    }

    return runpod_input


def handler(job):
    """
    The main handler function for the RunPod serverless worker.
    """
    job_input = job["input"]

    try:
        # 1. Prepare and execute the image generation job on the RunPod endpoint.
        runpod_input = prepare_runpod_input(job_input)
        runpod_output = endpoint.run_sync(runpod_input)

        images = runpod_output.get("images")
        if not images or len(images) != 1:
            raise ValueError(
                f"Endpoint returned no image or multiple images. Output: {runpod_output}"
            )

        base64_image = images[0].get("data")
        if not base64_image:
            raise ValueError("Returned image data is empty or malformed.")

        # 2. Upload the resulting image to Cloudflare and get its public URL.
        unique_id = uuid.uuid4().hex
        image_bytes = base64.b64decode(base64_image)

        api_url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/images/v1"
        headers = {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"}
        files = {"file": (f"{unique_id}.png", image_bytes, "image/png")}

        response = requests.post(api_url, headers=headers, files=files)
        response.raise_for_status()

        upload_result = response.json()
        variants = upload_result.get("result", {}).get("variants")
        if not variants:
            raise ValueError(
                f"Cloudflare response is missing image variants. Response: {upload_result}"
            )

        return {"image_url": variants[0]}

    # 3. Catch any expected or unexpected errors and return a clean error response.
    except ValueError as e:
        return {"error": str(e)}
    except requests.exceptions.HTTPError as e:
        return {
            "error": f"Cloudflare API Error: {e.response.status_code} - {e.response.text}"
        }
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return {"error": "An internal server error occurred."}


runpod.serverless.start({"handler": handler})
