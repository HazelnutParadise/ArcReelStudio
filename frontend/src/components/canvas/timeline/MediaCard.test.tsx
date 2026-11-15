import { fireEvent, render, screen } from "@testing-library/react";
import { API } from "@/api";
import type { PresentationReadModel } from "@/types/presentation";
import { afterEach, describe, expect, it, vi } from "vite-plus/test";
import { DEMO_PROJECT_NAME } from "@/onboarding/demo-project";
import { useProjectsStore } from "@/stores/projects-store";
import { MediaCard } from "./MediaCard";

function renderCard(props: Partial<Parameters<typeof MediaCard>[0]> = {}) {
  return render(
    <MediaCard kind="storyboard" projectName="demo" segmentId="E1S01" assetPath={null} aspectRatio="9:16" {...props} />,
  );
}

describe("MediaCard storyboard image", () => {
  afterEach(() => useProjectsStore.setState({ assetFingerprints: {} }));

  it("offers 640 and 1280 thumbnails to the card and keeps the original for the full-screen preview", () => {
    useProjectsStore.setState({ assetFingerprints: { "storyboards/E1S01.png": 5 } });
    renderCard({ assetPath: "storyboards/E1S01.png" });

    const card = screen.getByRole("img", { name: /分镜图$/ });
    expect(card).toHaveAttribute(
      "srcset",
      "/api/v1/files/demo/storyboards/E1S01.png?v=5&w=640 640w, /api/v1/files/demo/storyboards/E1S01.png?v=5&w=1280 1280w",
    );
    expect(card).toHaveAttribute("src", "/api/v1/files/demo/storyboards/E1S01.png?v=5");

    fireEvent.click(screen.getByRole("button", { name: /分镜图」的大图$/ }));
    const preview = screen.getAllByRole("img", { name: /分镜图$/ }).find((img) => !img.hasAttribute("srcset"));
    expect(preview).toHaveAttribute("src", "/api/v1/files/demo/storyboards/E1S01.png?v=5");
  });
});

describe("MediaCard video length", () => {
  afterEach(() => vi.restoreAllMocks());

  function mockVideoLength(seconds: number) {
    vi.spyOn(API, "getPresentation").mockResolvedValue({
      schema_version: 1,
      provenance: "verified",
      episode: 1,
      resource_type: "videos",
      script_file: "episode_1.json",
      subtitle_artifact_path: null,
      presentation_artifact_path: null,
      persisted: true,
      unit_id: "E1S01",
      variant: "post_production",
      speech_mode: "silent",
      selection: "current",
      currency: "current",
      video: {
        artifact_path: "videos/scene_E1S01.mp4",
        version: 1,
        selection: "current",
        currency: "current",
        basis: null,
        content_digest: "sha256-v1:video",
        actual_duration_seconds: seconds,
        start_microseconds: 0,
        duration_microseconds: seconds * 1_000_000,
        audio_enabled: true,
        gain: 1,
      },
      narration_audio: null,
      subtitles: [],
      subtitle_basis: null,
      presentation_basis: null,
      timing: "mechanical",
      subtitles_adjustable: false,
      subtitles_webvtt: "WEBVTT\n",
    } as PresentationReadModel);
  }

  it("says when the uploaded video is not as long as the shot and that the edit timeline uses the real length", async () => {
    mockVideoLength(4);
    renderCard({ kind: "video", assetPath: "videos/scene_E1S01.mp4", plannedDurationSeconds: 8 });

    expect(await screen.findByText("视频实际 4 秒，分镜时长是 8 秒。剪辑时间轴按实际长度排")).toBeInTheDocument();
  });

  it("says nothing when the video matches the shot length", async () => {
    mockVideoLength(8.02);
    renderCard({ kind: "video", assetPath: "videos/scene_E1S01.mp4", plannedDurationSeconds: 8 });

    await vi.waitFor(() => expect(API.getPresentation).toHaveBeenCalled());
    expect(screen.queryByText(/视频实际/)).not.toBeInTheDocument();
  });
});

describe("MediaCard upload", () => {
  it("invokes onUpload with the selected file", () => {
    const onUpload = vi.fn();
    const { container } = renderCard({ onUpload });
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    const file = new File(["x"], "board.png", { type: "image/png" });
    fireEvent.change(input!, { target: { files: [file] } });
    expect(onUpload).toHaveBeenCalledWith(file);
  });

  it("hides upload entry when onUpload is not provided", () => {
    const { container } = renderCard();
    expect(container.querySelector('input[type="file"]')).toBeNull();
  });

  it("disables upload button while generating", () => {
    renderCard({ onUpload: vi.fn(), generating: true });
    expect(screen.getByRole("button", { name: "上传分镜图" })).toBeDisabled();
  });

  it("disables upload button when a sibling upload is in flight (uploadDisabled)", () => {
    renderCard({ onUpload: vi.fn(), uploadDisabled: true });
    expect(screen.getByRole("button", { name: "上传分镜图" })).toBeDisabled();
  });

  it("accepts video formats for the video card", () => {
    const { container } = renderCard({ kind: "video", onUpload: vi.fn() });
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input?.accept).toContain(".mp4");
  });

  it("disables the generate CTA when a sibling upload is in flight (uploadDisabled)", () => {
    const { getByRole } = renderCard({ onGenerate: vi.fn(), uploadDisabled: true });
    expect(getByRole("button", { name: /生成分镜/ })).toBeDisabled();
  });
});

describe("MediaCard in the demo workbench", () => {
  afterEach(() => {
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
  });

  // 四个入口的回调/开关全部给足：只有演示态判定本身能把它们关掉
  function renderCardWithAllEntries() {
    return renderCard({
      assetPath: "storyboards/E1S01_v1.png",
      onUpload: vi.fn(),
      onRestore: vi.fn(),
      onGenerate: vi.fn(),
      editScriptFile: "episode_1.json",
    });
  }

  it("hides the write entries and the version entry from the same judgement", () => {
    useProjectsStore.setState({ currentProjectName: DEMO_PROJECT_NAME });

    const { container, queryByRole } = renderCardWithAllEntries();

    expect(container.querySelector('input[type="file"]')).toBeNull();
    expect(queryByRole("button", { name: /版本/ })).not.toBeInTheDocument();
    expect(queryByRole("button", { name: /编辑/ })).not.toBeInTheDocument();
    expect(queryByRole("button", { name: /重新生成分镜/ })).not.toBeInTheDocument();
  });

  it("keeps all four entries outside the demo workbench", () => {
    useProjectsStore.setState({ currentProjectName: "demo" });

    const { container, getByRole } = renderCardWithAllEntries();

    expect(container.querySelector('input[type="file"]')).not.toBeNull();
    expect(getByRole("button", { name: /版本/ })).toBeInTheDocument();
    expect(getByRole("button", { name: /局部修改/ })).toBeInTheDocument();
    expect(getByRole("button", { name: /重新生成分镜/ })).toBeInTheDocument();
  });
});
