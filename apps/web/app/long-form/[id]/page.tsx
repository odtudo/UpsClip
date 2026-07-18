import { LongformWorkflow } from "@/components/workflows/longform-workflow";
export default async function LongformProjectPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <LongformWorkflow analysisId={id} />;
}
