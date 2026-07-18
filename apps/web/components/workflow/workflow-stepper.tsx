import type { WorkflowStep } from "@/types/workflow";
import { Icon } from "@/components/ui/icons";

export function WorkflowStepper({
  steps,
  current,
}: {
  steps: Array<{ id: WorkflowStep; label: string }>;
  current: WorkflowStep;
}) {
  const active = steps.findIndex((step) => step.id === current);
  return (
    <nav aria-label="Workflow progress" className="mb-8 overflow-x-auto">
      <ol className="flex min-w-max items-center">
        {steps.map((step, index) => (
          <li key={step.id} className="flex items-center">
            <div
              className={`flex items-center gap-2 text-xs font-semibold ${index === active ? "text-primary" : index < active ? "text-success" : "text-muted"}`}
            >
              <span
                className={`grid h-7 w-7 place-items-center rounded-full border ${index === active ? "border-accent bg-accent/15 text-accentSoft" : index < active ? "border-success/50 bg-success/10" : "border-line bg-card"}`}
              >
                {index < active ? (
                  <Icon name="check" className="h-4 w-4" />
                ) : (
                  index + 1
                )}
              </span>
              <span>{step.label}</span>
            </div>
            {index < steps.length - 1 && (
              <span
                className={`mx-3 h-px w-7 ${index < active ? "bg-success/50" : "bg-line"}`}
              />
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
