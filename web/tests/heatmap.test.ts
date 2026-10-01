import { describe, expect, it } from "vitest";
import { scaleTop } from "../src/heatmap";

describe("heatmap colour scale", () => {
  const small = Float32Array.from([0.01, 0.03, 0.05]);       // tiny variation
  it("floor: values below 20% are not stretched", () => {
    expect(scaleTop(small, 1, 0.2, false)).toBe(0.2);
  });
  it("per-map: a nice step at or above the data maximum", () => {
    expect(scaleTop(Float32Array.from([0.1, 0.33]), 1, 0.2, false)).toBe(0.4);
    expect(scaleTop(Float32Array.from([0.9]), 1, 0.2, false)).toBe(1);
  });
  it("never above the ceiling; cost floor scales with the weights", () => {
    expect(scaleTop(Float32Array.from([0.05]), 2, 0.4, false)).toBe(0.4);
    expect(scaleTop(Float32Array.from([1.7]), 2, 0.4, false)).toBe(2);
  });
  it("fixed toggle: always the full range", () => {
    expect(scaleTop(small, 1, 0.2, true)).toBe(1);
    expect(scaleTop(small, 2, 0.4, true)).toBe(2);
  });
});
