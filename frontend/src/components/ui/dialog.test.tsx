import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vite-plus/test";
import { Dialog, DialogBody, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "./dialog";

describe("Dialog", () => {
  // 焦点守卫把焦点送回弹层是在下一帧完成的，每次 Tab 之后等一帧再断言
  it("keeps Tab focus inside the open dialog", async () => {
    const user = userEvent.setup();
    render(
      <>
        <button type="button">outside before</button>
        <Dialog open>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Title</DialogTitle>
            </DialogHeader>
            <DialogBody>
              <input aria-label="first" />
            </DialogBody>
            <DialogFooter>
              <button type="button">last</button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
        <button type="button">outside after</button>
      </>,
    );
    const dialog = await screen.findByRole("dialog");
    screen.getByRole("textbox", { name: "first" }).focus();
    for (let i = 0; i < 8; i += 1) {
      await user.tab();
      await act(() => new Promise((resolve) => requestAnimationFrame(resolve)));
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
    for (let i = 0; i < 8; i += 1) {
      await user.tab({ shift: true });
      await act(() => new Promise((resolve) => requestAnimationFrame(resolve)));
      expect(dialog.contains(document.activeElement)).toBe(true);
    }
  });
});
