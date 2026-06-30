"use client";

import { gql, useMutation, useQuery } from "@apollo/client";
import { useState } from "react";

import { AdminErrorBanner } from "../../../components/AdminErrorBanner";
import { formatMutationError } from "../../../lib/mutation-error";

const GLOSSARY = gql`
  query BusinessGlossary {
    businessGlossary {
      id
      term
      definition
      aliases
      isIndexed
    }
  }
`;

const KNOWLEDGE = gql`
  query KnowledgeEntries($datasourceId: Int) {
    knowledgeEntries(datasourceId: $datasourceId) {
      id
      category
      title
      content
      isIndexed
    }
  }
`;

const DATASOURCES = gql`
  query Datasources {
    datasources {
      id
      name
    }
  }
`;

const CREATE_GLOSSARY = gql`
  mutation CreateGlossary($input: CreateGlossaryInput!) {
    createGlossary(input: $input) {
      id
    }
  }
`;

const DELETE_GLOSSARY = gql`
  mutation DeleteGlossary($glossaryId: Int!) {
    deleteGlossary(glossaryId: $glossaryId)
  }
`;

const CREATE_KNOWLEDGE = gql`
  mutation CreateKnowledge($input: CreateKnowledgeInput!) {
    createKnowledge(input: $input) {
      id
    }
  }
`;

const DELETE_KNOWLEDGE = gql`
  mutation DeleteKnowledge($entryId: Int!) {
    deleteKnowledge(entryId: $entryId)
  }
`;

const INDEX_ITEM = gql`
  mutation IndexItem($input: IndexItemInput!) {
    indexItem(input: $input)
  }
`;

const UNINDEX_ITEM = gql`
  mutation UnindexItem($input: IndexItemInput!) {
    unindexItem(input: $input)
  }
`;

export default function BusinessPage() {
  const [selectedDs, setSelectedDs] = useState<number | null>(null);
  const [newTerm, setNewTerm] = useState({ term: "", definition: "", aliases: "" });
  const [newKnowledge, setNewKnowledge] = useState({ title: "", content: "", category: "faq" });
  const [error, setError] = useState<string | null>(null);

  const { data: dsData } = useQuery(DATASOURCES);
  const { data: glossaryData, refetch: refetchGlossary } = useQuery(GLOSSARY);
  const { data: knowledgeData, refetch: refetchKnowledge } = useQuery(KNOWLEDGE, {
    variables: { datasourceId: selectedDs },
  });

  const [createGlossary] = useMutation(CREATE_GLOSSARY);
  const [deleteGlossary] = useMutation(DELETE_GLOSSARY);
  const [createKnowledge] = useMutation(CREATE_KNOWLEDGE);
  const [deleteKnowledge] = useMutation(DELETE_KNOWLEDGE);
  const [indexItem] = useMutation(INDEX_ITEM);
  const [unindexItem] = useMutation(UNINDEX_ITEM);

  const glossary = glossaryData?.businessGlossary || [];
  const knowledge = knowledgeData?.knowledgeEntries || [];
  const datasources = dsData?.datasources || [];

  const toggleGlossaryIndex = async (id: number, indexed: boolean) => {
    try {
      setError(null);
      const input = { docType: "glossary", sourceId: id };
      if (indexed) await unindexItem({ variables: { input } });
      else await indexItem({ variables: { input } });
      refetchGlossary();
    } catch (err) {
      setError(formatMutationError(err));
    }
  };

  const toggleKnowledgeIndex = async (id: number, indexed: boolean) => {
    try {
      setError(null);
      const input = { docType: "knowledge", sourceId: id };
      if (indexed) await unindexItem({ variables: { input } });
      else await indexItem({ variables: { input } });
      refetchKnowledge();
    } catch (err) {
      setError(formatMutationError(err));
    }
  };

  return (
    <div>
      <h1 className="page-title">业务数据</h1>
      <AdminErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="card">
        <h3>业务术语</h3>
        <div className="form-row">
          <input
            placeholder="术语"
            value={newTerm.term}
            onChange={(e) => setNewTerm({ ...newTerm, term: e.target.value })}
          />
          <input
            placeholder="定义"
            value={newTerm.definition}
            onChange={(e) => setNewTerm({ ...newTerm, definition: e.target.value })}
          />
          <button
            className="btn"
            onClick={async () => {
              try {
                setError(null);
                await createGlossary({
                  variables: {
                    input: {
                      term: newTerm.term,
                      definition: newTerm.definition,
                      aliases: newTerm.aliases || null,
                    },
                  },
                });
                setNewTerm({ term: "", definition: "", aliases: "" });
                refetchGlossary();
              } catch (err) {
                setError(formatMutationError(err));
              }
            }}
          >
            添加术语
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>术语</th>
              <th>定义</th>
              <th>已索引</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {glossary.map(
              (g: { id: number; term: string; definition: string; isIndexed: boolean }) => (
                <tr key={g.id}>
                  <td>{g.term}</td>
                  <td>{g.definition}</td>
                  <td>{g.isIndexed ? "是" : "否"}</td>
                  <td>
                    <button
                      className="btn btn-sm"
                      onClick={() => toggleGlossaryIndex(g.id, g.isIndexed)}
                    >
                      {g.isIndexed ? "取消索引" : "入库"}
                    </button>
                    <button
                      className="btn btn-sm"
                      style={{ marginLeft: "0.5rem" }}
                      onClick={async () => {
                        try {
                          setError(null);
                          await deleteGlossary({ variables: { glossaryId: g.id } });
                          refetchGlossary();
                        } catch (err) {
                          setError(formatMutationError(err));
                        }
                      }}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>FAQ / 知识库</h3>
        <div className="form-group">
          <label>数据源（可选，留空为全局）</label>
          <select
            value={selectedDs ?? ""}
            onChange={(e) => setSelectedDs(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">全局</option>
            {datasources.map((ds: { id: number; name: string }) => (
              <option key={ds.id} value={ds.id}>
                {ds.name}
              </option>
            ))}
          </select>
        </div>
        <div className="form-row">
          <input
            placeholder="标题"
            value={newKnowledge.title}
            onChange={(e) => setNewKnowledge({ ...newKnowledge, title: e.target.value })}
          />
          <textarea
            placeholder="内容"
            value={newKnowledge.content}
            onChange={(e) => setNewKnowledge({ ...newKnowledge, content: e.target.value })}
          />
          <button
            className="btn"
            onClick={async () => {
              try {
                setError(null);
                await createKnowledge({
                  variables: {
                    input: {
                      title: newKnowledge.title,
                      content: newKnowledge.content,
                      category: newKnowledge.category,
                      datasourceId: selectedDs,
                    },
                  },
                });
                setNewKnowledge({ title: "", content: "", category: "faq" });
                refetchKnowledge();
              } catch (err) {
                setError(formatMutationError(err));
              }
            }}
          >
            添加知识
          </button>
        </div>
        <table>
          <thead>
            <tr>
              <th>标题</th>
              <th>分类</th>
              <th>已索引</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {knowledge.map(
              (k: { id: number; title: string; category: string; isIndexed: boolean }) => (
                <tr key={k.id}>
                  <td>{k.title}</td>
                  <td>{k.category}</td>
                  <td>{k.isIndexed ? "是" : "否"}</td>
                  <td>
                    <button
                      className="btn btn-sm"
                      onClick={() => toggleKnowledgeIndex(k.id, k.isIndexed)}
                    >
                      {k.isIndexed ? "取消索引" : "入库"}
                    </button>
                    <button
                      className="btn btn-sm"
                      style={{ marginLeft: "0.5rem" }}
                      onClick={async () => {
                        try {
                          setError(null);
                          await deleteKnowledge({ variables: { entryId: k.id } });
                          refetchKnowledge();
                        } catch (err) {
                          setError(formatMutationError(err));
                        }
                      }}
                    >
                      删除
                    </button>
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
