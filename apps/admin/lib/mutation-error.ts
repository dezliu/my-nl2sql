import { ApolloError } from "@apollo/client";

export function formatMutationError(err: unknown): string {
  if (err instanceof ApolloError) {
    const gqlMsg = err.graphQLErrors[0]?.message;
    if (gqlMsg) return gqlMsg;
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}
