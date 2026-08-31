import { useState, type KeyboardEvent } from "react";

interface TagInputProps {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  tagClassName?: string;
}

export default function TagInput({ values, onChange, placeholder, tagClassName = "tag-blue" }: TagInputProps) {
  const [input, setInput] = useState("");

  const add = () => {
    const v = input.trim();
    if (!v) return;
    onChange([...values, v]);
    setInput("");
  };

  const remove = (idx: number) => {
    onChange(values.filter((_, i) => i !== idx));
  };

  const handleKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") { e.preventDefault(); add(); }
  };

  return (
    <>
      <div className="tag-input-row" style={{ marginBottom: 8 }}>
        <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKey} placeholder={placeholder} />
        <button type="button" className="btn btn-secondary" onClick={add}>添加</button>
      </div>
      <div>
        {values.map((v, i) => (
          <span key={i} className={`tag ${tagClassName}`} onClick={() => remove(i)} style={{ cursor: "pointer" }} title="点击删除">
            {v} ×
          </span>
        ))}
      </div>
    </>
  );
}
