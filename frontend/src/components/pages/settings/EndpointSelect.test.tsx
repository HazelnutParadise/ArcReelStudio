import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";
import { API } from "@/api";
import { useEndpointCatalogStore } from "@/stores/endpoint-catalog-store";
import type { EndpointDescriptor } from "@/types";
import { EndpointSelect } from "./EndpointSelect";

function videoEndpoint(key: string, displayName: string, extra: Partial<EndpointDescriptor> = {}): EndpointDescriptor {
  return {
    key,
    media_type: "video",
    family: "google",
    kind: "python",
    source: "builtin",
    display_name_key: `endpoint_${key}_display`,
    display_name: displayName,
    request_method: "POST",
    request_path_template: `/${key}`,
    image_capabilities: null,
    end_image_capable: false,
    custom_selectable: true,
    size_fixed: false,
    duration_fixed: false,
    duration_frame_rate_missing: false,
    duration_tier_empty: false,
    native_resolution: null,
    requests: [],
    ...extra,
  };
}

const OMNI = videoEndpoint("gemini-interactions-video", "Gemini Omni");
const RELAY_VEO = videoEndpoint("gemini-video", "Veo via Gemini", { custom_selectable: false });

describe("EndpointSelect", () => {
  beforeEach(() => {
    useEndpointCatalogStore.setState(useEndpointCatalogStore.getInitialState(), true);
    vi.spyOn(API, "listEndpointCatalog").mockResolvedValue({ endpoints: [OMNI, RELAY_VEO] });
  });

  it("does not offer retired endpoints such as Veo through a Gemini relay", async () => {
    render(<EndpointSelect aria-label="调用端点" value={OMNI.key} onChange={vi.fn()} protocol="google" />);
    await waitFor(() => expect(useEndpointCatalogStore.getState().initialized).toBe(true));

    await userEvent.setup().click(screen.getByRole("combobox", { name: "调用端点" }));

    expect(await screen.findByRole("option", { name: /Gemini Omni/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Veo via Gemini/ })).not.toBeInTheDocument();
  });

  it("still shows a retired endpoint that an existing model already uses", async () => {
    render(<EndpointSelect aria-label="调用端点" value={RELAY_VEO.key} onChange={vi.fn()} protocol="google" />);
    await waitFor(() => expect(useEndpointCatalogStore.getState().initialized).toBe(true));

    expect(screen.getByRole("combobox", { name: "调用端点" })).toHaveTextContent("Veo via Gemini");
  });
});
