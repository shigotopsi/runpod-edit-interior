# API Endpoint Specification

## 1. Overview

This document provides the technical specification for the API endpoint.

The operational flow is as follows:

1.  The back-end service sends a `POST` request with a specified JSON payload to the endpoint.
2.  The request is processed synchronously.
3.  The API generates an image, uploads it to the Cloudflare Images account, and returns a direct, publicly accessible URL to the final asset.

## 2. API Endpoint

`POST https://api.runpod.ai/v2/{ENDPOINT_ID}/runsync`

## 3. Configuration Record

The following environment variables must be configured as secrets in the RunPod pod for the service to function correctly.

- `RUNPOD_API_KEY`: The API key for the RunPod account.
- `ENDPOINT_ID`: The ID of the specific RunPod endpoint this service is deployed to.
- `CLOUDFLARE_ACCOUNT_ID`: The Cloudflare Account ID.
- `CLOUDFLARE_API_TOKEN`: The Cloudflare API Token with image write permissions.

## 4. Workflows and Parameters

The API supports two primary workflows: `virtual_staging` and `interior_redesign`.

#### Supported `room` Types

- `living_room`
- `bedroom`
- `kitchen`
- `bathroom`

#### Supported `style` Types

- `biophilic`
- `bohemian`
- `christmas`
- `coastal`
- `contemporary`
- `cottagecore`
- `cyberpunk`
- `easter`
- `eclectic`
- `farmhouse`
- `french_country`
- `gamer`
- `halloween`
- `industrial`
- `italian`
- `japandi`
- `japanese`
- `maximalist`
- `medieval`
- `midcentury_modern`
- `minimalist`
- `modern`
- `neoclassic`
- `rustic`
- `scandinavian`
- `ski_chalet`
- `vaporwave`
- `vintage`
- `vineyard`
- `zen`

---

### 4.1. Virtual Staging

This workflow populates an image of an empty room with furniture and decor.

#### Minimalist Example

```json
{
  "input": {
    "image_url": "https://www.example.com/empty-room.jpg",
    "room": "living_room",
    "style": "modern",
    "workflow": "virtual_staging"
  }
}
```

#### Virtual Staging Parameters

| Parameter                 | Type    | Description                                                   | Required | Default Value   |
| :------------------------ | :------ | :------------------------------------------------------------ | :------- | :-------------- |
| `input.image_url`         | String  | Public URL to the source image of the empty room.             | **Yes**  | N/A             |
| `input.room`              | String  | The type of room. See supported list above.                   | **Yes**  | N/A             |
| `input.style`             | String  | The style of furniture. See supported list above.             | **Yes**  | N/A             |
| `input.workflow`          | String  | Must be set to `"virtual_staging"`.                           | **Yes**  | N/A             |
| `input.parameters`        | Object  | Optional container for technical parameters.                  | No       | System defaults |
| `parameters.version`      | String  | The version of the base workflow definition to use.           | No       | `"1.0.0"`       |
| `parameters.seed`         | Integer | A seed for the random number generator.                       | No       | `1`             |
| `parameters.steps`        | Integer | The number of generation steps.                               | No       | `20`            |
| `parameters.guidance`     | Float   | Controls how closely the image follows the prompt (CFG).      | No       | `3.0`           |
| `parameters.sampler_name` | String  | The sampling algorithm.                                       | No       | `"euler"`       |
| `parameters.scheduler`    | String  | The noise scheduler.                                          | No       | `"beta"`        |
| `parameters.denoise`      | Float   | `0.0` to `1.0`. Controls alteration from the original.        | No       | `1.0`           |
| `parameters.hires`        | Object  | Enables a high-resolution pass. See details in **Section 5**. | No       | Disabled        |

---

### 4.2. Interior Redesign

This workflow redesigns an existing room based on a new style, keeping the original layout and structure.

#### Minimalist Example

```json
{
  "input": {
    "image_url": "https://www.example.com/furnished-room.jpg",
    "room": "bedroom",
    "style": "industrial",
    "workflow": "interior_redesign"
  }
}
```

#### Interior Redesign Parameters

| Parameter                 | Type    | Description                                                   | Required | Default Value   |
| :------------------------ | :------ | :------------------------------------------------------------ | :------- | :-------------- |
| `input.image_url`         | String  | Public URL to the source image to be redesigned.              | **Yes**  | N/A             |
| `input.room`              | String  | The type of room. See supported list above.                   | **Yes**  | N/A             |
| `input.style`             | String  | The target design style. See supported list above.            | **Yes**  | N/A             |
| `input.workflow`          | String  | Must be set to `"interior_redesign"`.                         | **Yes**  | N/A             |
| `input.parameters`        | Object  | Optional container for technical parameters.                  | No       | System defaults |
| `parameters.version`      | String  | The version of the base workflow definition to use.           | No       | `"1.0.0"`       |
| `parameters.controlnet`   | Object  | **(Redesign Only)** Fine-tunes structure preservation.        | No       | System defaults |
| `parameters.seed`         | Integer | A seed for the random number generator.                       | No       | `1`             |
| `parameters.steps`        | Integer | The number of generation steps.                               | No       | `20`            |
| `parameters.guidance`     | Float   | Controls how closely the image follows the prompt (CFG).      | No       | `3.5`           |
| `parameters.sampler_name` | String  | The sampling algorithm.                                       | No       | `"euler"`       |
| `parameters.scheduler`    | String  | The noise scheduler.                                          | No       | `"beta"`        |
| `parameters.denoise`      | Float   | `0.0` to `1.0`. Controls alteration from the original.        | No       | `1.0`           |
| `parameters.mask`         | Object  | **(Redesign Only)** Applies changes to a specific area.       | No       | Disabled        |
| `parameters.hires`        | Object  | Enables a high-resolution pass. See details in **Section 5**. | No       | Disabled        |

---

## 5. Parameter Modules

These are complex objects that can be included within the `parameters` block to enable advanced features.

### 5.1. ControlNet Module (`parameters.controlnet`)

_Applies to: `interior_redesign`_

| Parameter     | Type  | Description                                                   | Required | Default Value |
| :------------ | :---- | :------------------------------------------------------------ | :------- | :------------ |
| `strength`    | Float | The weight of the ControlNet guidance.                        | No       | `0.6`         |
| `end_percent` | Float | The percentage of steps at which to stop ControlNet guidance. | No       | `0.6`         |

### 5.2. Mask Module (`parameters.mask`)

_Applies to: `interior_redesign`_

| Parameter | Type    | Description                                                        | Required | Default Value |
| :-------- | :------ | :----------------------------------------------------------------- | :------- | :------------ |
| `enabled` | Boolean | Set to `true` to activate the mask.                                | No       | `false`       |
| `type`    | String  | The source of the mask. Currently supports `"prompt"` and `"url"`. | No       | `""`          |
| `value`   | String  | The prompt text or a URL to a black and white mask image.          | No       | `""`          |

### 5.3. Hi-Res Fix Module (`parameters.hires`)

_Applies to: `All Workflows`_

Enabling this module triggers a second processing pass to upscale the image and add detail.

| Parameter      | Type    | Description                                              | Required | Default Value |
| :------------- | :------ | :------------------------------------------------------- | :------- | :------------ |
| `enabled`      | Boolean | Set to `true` to activate the hi-res fix.                | No       | `false`       |
| `version`      | String  | The version of the hi-res fix workflow definition.       | No       | `"1.0.0"`     |
| `scale_by`     | Float   | The factor by which to scale the image (e.g., `1.5`).    | No       | `1.0`         |
| `seed`         | Integer | The seed for the upscaling pass.                         | No       | `1`           |
| `steps`        | Integer | The number of steps for the upscaling pass.              | No       | `20`          |
| `guidance`     | Float   | The CFG scale for the upscaling pass.                    | No       | `3.5`         |
| `sampler_name` | String  | The sampling algorithm for the upscaling pass.           | No       | `"euler"`     |
| `scheduler`    | String  | The noise scheduler for the upscaling pass.              | No       | `"beta"`      |
| `denoise`      | Float   | Denoising strength for the upscaling pass (`0.0`-`1.0`). | No       | `0.4`         |

---

## 6. API Response

The API will return a JSON body containing the direct URL to the generated image.

```json
{
  "image_url": "https://imagedelivery.net/{CLOUDFLARE_ACCOUNT_HASH}/{UNIQUE_ID}/public"
}
```
