# Base image
FROM runpod/worker-comfyui:5.2.0-base

# Custom nodes
RUN comfy-node-install comfyui_controlnet_aux
RUN comfy-node-install comfyui-florence2

# Diffusion models
RUN comfy model download --url https://huggingface.co/Kijai/flux-fp8/resolve/main/flux1-dev-fp8.safetensors --relative-path models/diffusion_models --filename flux1-dev-fp8.safetensors
RUN comfy model download --url https://huggingface.co/GraydientPlatformAPI/flux-inpainting-faster/resolve/main/flux-fill-inpainting-fp8-yogotatara.safetensors --relative-path models/diffusion_models --filename flux1-fill-fp8.safetensors
RUN comfy model download --url https://huggingface.co/Comfy-Org/flux1-kontext-dev_ComfyUI/resolve/main/split_files/diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors --relative-path models/diffusion_models --filename flux1-dev-kontext_fp8_scaled.safetensors

# Controlnet
RUN comfy model download --url https://huggingface.co/Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro-2.0/resolve/main/diffusion_pytorch_model.safetensors --relative-path models/controlnet --filename flux1-control-union-pro2.0.safetensors

# Text encoders
RUN comfy model download --url https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors --relative-path models/text_encoders --filename clip_l.safetensors
RUN comfy model download --url https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors --relative-path models/text_encoders --filename t5xxl_fp8_e4m3fn_scaled.safetensors

# VAE
RUN comfy model download --url https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors --relative-path models/vae --filename ae.safetensors

# LLM (Florence-2)
RUN huggingface-cli download \
    microsoft/Florence-2-large-ft \
    --local-dir /comfyui/models/LLM/Florence-2-large-ft \
    --local-dir-use-symlinks False

# Copy local files
COPY prompts/ /prompts
COPY workflows/ /workflows
COPY handler.py handler.py