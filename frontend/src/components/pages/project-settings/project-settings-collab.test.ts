import { describe, expect, it } from "vite-plus/test";

import type { UnitJson } from "@/collab/ydoc-json";

import type { GlobalModelDefaults, ProjectFacts } from "./project-settings-form";
import { projectSettingsFromUnit, projectSettingsToUnit } from "./project-settings-collab";

const GLOBALS: GlobalModelDefaults = {
  video: "",
  videoI2V: "",
  videoR2V: "",
  image: "",
  imageT2I: "",
  imageI2I: "",
  textDefault: "",
  textSimple: "",
  textComplex: "",
};
const FACTS: ProjectFacts = { contentMode: "narration", generationRoute: "storyboard" };
const options = { projectName: "demo", facts: FACTS, globals: GLOBALS };

function stored(overrides: UnitJson = {}): UnitJson {
  return {
    aspect_ratio: "9:16",
    grid_storyboard: false,
    speech_rate_units_per_second: null,
    episode_target_duration: null,
    default_duration: null,
    video_backend: null,
    narration_delivery: "post_production",
    style_template_id: null,
    style_image: null,
    style_description: null,
    model_settings: null,
    ...overrides,
  };
}

describe("project settings in a collaboration room", () => {
  it("reads the form from the stored fields", () => {
    const form = projectSettingsFromUnit(stored({ aspect_ratio: "16:9", speech_rate_units_per_second: 4.5 }), options);
    expect(form.aspectRatio).toBe("16:9");
    expect(form.speechRate).toBe(4.5);
    expect(form.style).toEqual({ kind: "none" });
  });

  it("writes only the fields that changed and keeps the rest of the room as it is", () => {
    const current = stored({ video_backend: "gemini-vertex/veo-3" });
    const form = projectSettingsFromUnit(current, options);

    const next = projectSettingsToUnit({ ...form, aspectRatio: "16:9" }, current, options);

    expect(next).toEqual({ ...current, aspect_ratio: "16:9" });
  });

  it("choosing a template clears the reference image in the same change", () => {
    const current = stored({ style_image: "style_reference.png", style_description: "水彩" });
    const form = projectSettingsFromUnit(current, options);

    const next = projectSettingsToUnit({ ...form, style: { kind: "template", templateId: "anime" } }, current, options);

    expect(next.style_template_id).toBe("anime");
    expect(next.style_image).toBe("");
    expect(next.style_description).toBe("");
  });

  it("removing the style clears both the template and the reference image", () => {
    const current = stored({ style_template_id: "anime" });
    const form = projectSettingsFromUnit(current, options);

    const next = projectSettingsToUnit({ ...form, style: { kind: "none" } }, current, options);

    expect(next.style_template_id).toBeNull();
    expect(next.style_image).toBe("");
  });

  it("does not write a pending reference image upload into the room", () => {
    const current = stored();
    const form = projectSettingsFromUnit(current, options);
    const file = new File(["x"], "style.png", { type: "image/png" });

    const next = projectSettingsToUnit(
      { ...form, style: { kind: "image", preview: "blob:demo", description: "", file } },
      current,
      options,
    );

    expect(next).toEqual(current);
  });
});
