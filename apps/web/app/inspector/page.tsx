import { VodInspector } from "@/components/vod-inspector";
export default function InspectorPage() {
  return (
    <div>
      <p className="eyebrow">Engineering tool</p>
      <h1 className="mt-2 text-3xl font-semibold">VOD Inspector</h1>
      <p className="mt-3 mb-8 text-secondary">
        Validate the legacy visual phase detector without changing the editorial
        workflow.
      </p>
      <VodInspector />
    </div>
  );
}
