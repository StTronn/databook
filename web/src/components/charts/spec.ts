// Python's chart registry (databook/src/databook/components.json) is the single source of truth for types/variants.
import spec from "../../../../src/databook/components.json"
import type { ChartBlock } from "@/types"

export type ChartSpec = typeof spec.chart
export type ChartType = keyof ChartSpec
export type Variant<T extends ChartType> = keyof ChartSpec[T]["variants"]

type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false
// Fails to compile if src/types.ts ChartBlock["type"] drifts from components.json.
true satisfies Same<ChartType, ChartBlock["type"]>
