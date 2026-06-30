"use client";

import { ApolloProvider } from "@apollo/client";
import { createApolloClient } from "@/lib/apollo";
import { useMemo } from "react";

export default function Providers({ children }: { children: React.ReactNode }) {
  const client = useMemo(() => createApolloClient(), []);
  return <ApolloProvider client={client}>{children}</ApolloProvider>;
}
