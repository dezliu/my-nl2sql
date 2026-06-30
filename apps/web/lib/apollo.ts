import { ApolloClient, InMemoryCache, HttpLink, split } from "@apollo/client";
import { GraphQLWsLink } from "@apollo/client/link/subscriptions";
import { getMainDefinition } from "@apollo/client/utilities";
import { createClient } from "graphql-ws";

const httpUri = process.env.NEXT_PUBLIC_GRAPHQL_URL || "http://localhost:8000/graphql";
const wsUri = process.env.NEXT_PUBLIC_GRAPHQL_WS_URL || "ws://localhost:8000/graphql";

export function createApolloClient() {
  const httpLink = new HttpLink({ uri: httpUri });

  const wsLink =
    typeof window !== "undefined"
      ? new GraphQLWsLink(
          createClient({
            url: wsUri,
          })
        )
      : null;

  const link =
    wsLink &&
    split(
      ({ query }) => {
        const definition = getMainDefinition(query);
        return (
          definition.kind === "OperationDefinition" &&
          definition.operation === "subscription"
        );
      },
      wsLink,
      httpLink
    );

  return new ApolloClient({
    link: link || httpLink,
    cache: new InMemoryCache(),
  });
}
