export type GoalStage = 1 | 2 | 3;

export function goalStage(args: {
  confirming: boolean;
  hasAnalysis: boolean;
  analyzing: boolean;
}): GoalStage {
  if (args.confirming) return 3;
  if (args.hasAnalysis || args.analyzing) return 2;
  return 1;
}
