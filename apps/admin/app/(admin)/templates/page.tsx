"use client";

import { gql, useMutation, useQuery } from "@apollo/client";
import { useState } from "react";

const DATASOURCES = gql`
  query Datasources {
    datasources {
      id
      name
    }
  }
`;

const TEMPLATES = gql`
  query SqlTemplates($datasourceId: Int!) {
    sqlTemplates(datasourceId: $datasourceId) {
      id
      question
      sqlText
      description
      isIndexed
    }
  }
`;

const RECOMMENDATIONS = gql`
  query TemplateRecommendations($status: String) {
    templateRecommendations(status: $status) {
      id
      question
      sqlText
      qualityScore
      status
    }
  }
`;

const CREATE_TEMPLATE = gql`
  mutation CreateTemplate($input: CreateTemplateInput!) {
    createTemplate(input: $input) {
      id
    }
  }
`;

const DELETE_TEMPLATE = gql`
  mutation DeleteTemplate($templateId: Int!) {
    deleteTemplate(templateId: $templateId)
  }
`;

const APPROVE_REC = gql`
  mutation ApproveTemplateRecommendation($recId: Int!) {
    approveTemplateRecommendation(recId: $recId) {
      id
    }
  }
`;

const REJECT_REC = gql`
  mutation RejectTemplateRecommendation($recId: Int!) {
    rejectTemplateRecommendation(recId: $recId)
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

export default function TemplatesPage() {
  const [selectedDs, setSelectedDs] = useState<number | null>(null);
  const [newTpl, setNewTpl] = useState({ question: "", sqlText: "", description: "" });

  const { data: dsData } = useQuery(DATASOURCES);
  const { data: tplData, refetch: refetchTpl } = useQuery(TEMPLATES, {
    variables: { datasourceId: selectedDs },
    skip: !selectedDs,
  });
  const { data: recData, refetch: refetchRec } = useQuery(RECOMMENDATIONS, {
    variables: { status: "pending" },
  });

  const [createTemplate] = useMutation(CREATE_TEMPLATE);
  const [deleteTemplate] = useMutation(DELETE_TEMPLATE);
  const [approveRec] = useMutation(APPROVE_REC);
  const [rejectRec] = useMutation(REJECT_REC);
  const [indexItem] = useMutation(INDEX_ITEM);
  const [unindexItem] = useMutation(UNINDEX_ITEM);

  const datasources = dsData?.datasources || [];
  const templates = tplData?.sqlTemplates || [];
  const recommendations = recData?.templateRecommendations || [];

  const toggleIndex = async (id: number, indexed: boolean) => {
    const input = { docType: "sql_template", sourceId: id };
    if (indexed) await unindexItem({ variables: { input } });
    else await indexItem({ variables: { input } });
    refetchTpl();
  };

  return (
    <div>
      <h1 className="page-title">SQL 模板</h1>

      <div className="card">
        <h3>待审核推荐</h3>
        <table>
          <thead>
            <tr>
              <th>问题</th>
              <th>SQL</th>
              <th>质量分</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {recommendations.map(
              (r: { id: number; question: string; sqlText: string; qualityScore: number }) => (
                <tr key={r.id}>
                  <td>{r.question}</td>
                  <td>
                    <code>{r.sqlText.slice(0, 80)}...</code>
                  </td>
                  <td>{r.qualityScore.toFixed(2)}</td>
                  <td>
                    <button
                      className="btn btn-sm"
                      onClick={() =>
                        approveRec({ variables: { recId: r.id } }).then(() => {
                          refetchRec();
                          refetchTpl();
                        })
                      }
                    >
                      批准
                    </button>
                    <button
                      className="btn btn-sm"
                      style={{ marginLeft: "0.5rem" }}
                      onClick={() =>
                        rejectRec({ variables: { recId: r.id } }).then(() => refetchRec())
                      }
                    >
                      拒绝
                    </button>
                  </td>
                </tr>
              )
            )}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="form-group">
          <label>数据源</label>
          <select
            value={selectedDs ?? ""}
            onChange={(e) => setSelectedDs(Number(e.target.value))}
          >
            <option value="">选择数据源</option>
            {datasources.map((ds: { id: number; name: string }) => (
              <option key={ds.id} value={ds.id}>
                {ds.name}
              </option>
            ))}
          </select>
        </div>

        {selectedDs && (
          <>
            <div className="form-row">
              <input
                placeholder="自然语言问题"
                value={newTpl.question}
                onChange={(e) => setNewTpl({ ...newTpl, question: e.target.value })}
              />
              <textarea
                placeholder="SQL"
                value={newTpl.sqlText}
                onChange={(e) => setNewTpl({ ...newTpl, sqlText: e.target.value })}
              />
              <button
                className="btn"
                onClick={() =>
                  createTemplate({
                    variables: {
                      input: {
                        datasourceId: selectedDs,
                        question: newTpl.question,
                        sqlText: newTpl.sqlText,
                        description: newTpl.description || null,
                      },
                    },
                  }).then(() => {
                    setNewTpl({ question: "", sqlText: "", description: "" });
                    refetchTpl();
                  })
                }
              >
                添加模板
              </button>
            </div>

            <table>
              <thead>
                <tr>
                  <th>问题</th>
                  <th>SQL</th>
                  <th>已索引</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {templates.map(
                  (t: {
                    id: number;
                    question: string;
                    sqlText: string;
                    isIndexed: boolean;
                  }) => (
                    <tr key={t.id}>
                      <td>{t.question}</td>
                      <td>
                        <code>{t.sqlText.slice(0, 80)}</code>
                      </td>
                      <td>{t.isIndexed ? "是" : "否"}</td>
                      <td>
                        <button
                          className="btn btn-sm"
                          onClick={() => toggleIndex(t.id, t.isIndexed)}
                        >
                          {t.isIndexed ? "取消索引" : "入库"}
                        </button>
                        <button
                          className="btn btn-sm"
                          style={{ marginLeft: "0.5rem" }}
                          onClick={() =>
                            deleteTemplate({ variables: { templateId: t.id } }).then(() =>
                              refetchTpl()
                            )
                          }
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  )
                )}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
