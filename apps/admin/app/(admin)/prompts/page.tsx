"use client";

import { gql, useMutation, useQuery } from "@apollo/client";
import { useState } from "react";

const PROMPTS_QUERY = gql`
  query Prompts($role: String) {
    prompts(role: $role) {
      id
      role
      version
      content
      isActive
    }
  }
`;

const PROMPT_VERSIONS = gql`
  query PromptVersions($role: String!) {
    promptVersions(role: $role) {
      id
      role
      version
      content
      isActive
    }
  }
`;

const CREATE_PROMPT = gql`
  mutation CreatePrompt($input: CreatePromptInput!) {
    createPrompt(input: $input) {
      id
      role
      version
      isActive
    }
  }
`;

const ACTIVATE_PROMPT = gql`
  mutation ActivatePrompt($promptId: Int!) {
    activatePrompt(promptId: $promptId) {
      id
      isActive
    }
  }
`;

const ROLES = [
  "intent_classifier",
  "rag_router",
  "query_expander",
  "retrieval_judge",
  "sql_generator",
  "react_reasoner",
  "sql_safety",
  "result_summarizer",
  "rag_scorer",
];

export default function PromptsPage() {
  const [selectedRole, setSelectedRole] = useState(ROLES[0]);
  const [editContent, setEditContent] = useState("");

  const { data, refetch } = useQuery(PROMPTS_QUERY, {
    variables: { role: selectedRole },
  });
  const { data: versionsData, refetch: refetchVersions } = useQuery(PROMPT_VERSIONS, {
    variables: { role: selectedRole },
  });

  const [createPrompt] = useMutation(CREATE_PROMPT);
  const [activatePrompt] = useMutation(ACTIVATE_PROMPT);

  const activePrompt = data?.prompts?.find((p: { isActive: boolean }) => p.isActive);
  const versions = versionsData?.promptVersions || [];

  const handleRoleChange = (role: string) => {
    setSelectedRole(role);
    setEditContent("");
  };

  const handleLoadActive = () => {
    if (activePrompt) setEditContent(activePrompt.content);
  };

  const handleSave = async () => {
    await createPrompt({
      variables: { input: { role: selectedRole, content: editContent, activate: true } },
    });
    refetch();
    refetchVersions();
  };

  const handleActivate = async (promptId: number) => {
    await activatePrompt({ variables: { promptId } });
    refetch();
    refetchVersions();
  };

  return (
    <div>
      <h1 className="page-title">Prompt 管理</h1>

      <div className="card">
        <div className="form-group">
          <label>角色</label>
          <select value={selectedRole} onChange={(e) => handleRoleChange(e.target.value)}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>

        {activePrompt && (
          <p style={{ marginBottom: "1rem", color: "#9ca3af" }}>
            当前激活版本: v{activePrompt.version}
          </p>
        )}

        <div className="form-group">
          <label>Prompt 内容</label>
          <textarea
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            placeholder="输入 Prompt 模板，支持 {question} 等变量"
          />
        </div>

        <button className="btn" onClick={handleLoadActive}>
          加载当前版本
        </button>
        <button className="btn" onClick={handleSave} style={{ marginLeft: "0.5rem" }}>
          保存新版本并激活
        </button>
      </div>

      <div className="card">
        <h3 style={{ marginBottom: "1rem" }}>版本历史</h3>
        <table>
          <thead>
            <tr>
              <th>版本</th>
              <th>状态</th>
              <th>内容预览</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {versions.map((v: { id: number; version: number; isActive: boolean; content: string }) => (
              <tr key={v.id}>
                <td>v{v.version}</td>
                <td>
                  <span className={`badge ${v.isActive ? "badge-active" : "badge-inactive"}`}>
                    {v.isActive ? "激活" : "历史"}
                  </span>
                </td>
                <td style={{ maxWidth: 400, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {v.content.slice(0, 100)}...
                </td>
                <td>
                  {!v.isActive && (
                    <button className="btn btn-sm" onClick={() => handleActivate(v.id)}>
                      激活
                    </button>
                  )}
                  <button
                    className="btn btn-sm"
                    style={{ marginLeft: "0.5rem" }}
                    onClick={() => setEditContent(v.content)}
                  >
                    编辑
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
