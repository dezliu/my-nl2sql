import { ApolloClient, InMemoryCache, HttpLink } from "@apollo/client";

export function createApolloClient() {
  return new ApolloClient({
    link: new HttpLink({
      uri: process.env.NEXT_PUBLIC_GRAPHQL_URL || "http://localhost:8000/graphql",
    }),
    cache: new InMemoryCache(),
  });
}
