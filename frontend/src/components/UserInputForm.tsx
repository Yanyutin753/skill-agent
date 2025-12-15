import { useState } from 'react';
import { Send } from 'lucide-react';
import type { UserInputField } from '@/types/agent';

interface UserInputFormProps {
  fields: UserInputField[];
  context?: string;
  onSubmit: (values: Record<string, any>) => void;
  onCancel: () => void;
}

export default function UserInputForm({ fields, context, onSubmit, onCancel }: UserInputFormProps) {
  const [values, setValues] = useState<Record<string, any>>(() => {
    const initial: Record<string, any> = {};
    fields.forEach(f => {
      if (f.field_type === 'bool') initial[f.field_name] = false;
      else initial[f.field_name] = '';
    });
    return initial;
  });

  const handleChange = (fieldName: string, fieldType: string, value: string | boolean) => {
    let parsed: any = value;
    if (fieldType === 'int') parsed = parseInt(value as string, 10) || 0;
    else if (fieldType === 'float') parsed = parseFloat(value as string) || 0;
    else if (fieldType === 'bool') parsed = value;
    setValues(prev => ({ ...prev, [fieldName]: parsed }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit(values);
  };

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 my-4">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-2 h-2 bg-black rounded-full animate-pulse" />
        <span className="text-sm font-medium text-gray-900">需要补充信息</span>
      </div>
      
      {context && (
        <p className="text-sm text-gray-500 mb-5">{context}</p>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {fields.map(field => (
          <div key={field.field_name}>
            <label className="block text-sm text-gray-700 mb-1.5">
              {field.field_description}
            </label>
            {field.field_type === 'bool' ? (
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={values[field.field_name] || false}
                  onChange={e => handleChange(field.field_name, field.field_type, e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300 text-black focus:ring-black"
                />
                <span className="text-sm text-gray-600">{field.field_name}</span>
              </label>
            ) : (
              <input
                type={field.field_type === 'int' || field.field_type === 'float' ? 'number' : 'text'}
                value={values[field.field_name] || ''}
                onChange={e => handleChange(field.field_name, field.field_type, e.target.value)}
                placeholder={field.field_name}
                className="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-gray-300 focus:border-gray-300 bg-gray-50"
              />
            )}
          </div>
        ))}

        <div className="flex gap-3 pt-3">
          <button
            type="submit"
            className="flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg text-sm font-medium hover:bg-gray-800 transition-colors"
          >
            <Send className="w-3.5 h-3.5" />
            提交
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-gray-500 text-sm font-medium hover:text-gray-700 transition-colors"
          >
            取消
          </button>
        </div>
      </form>
    </div>
  );
}
