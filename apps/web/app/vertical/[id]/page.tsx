import { VerticalWorkflow } from "@/components/workflows/vertical-workflow";
export default async function VerticalProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <VerticalWorkflow previewId={id} />;
}
