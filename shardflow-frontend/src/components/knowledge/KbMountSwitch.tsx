import { useEffect, useState } from 'react';
import { Select, Switch, Space, Typography, Tooltip } from 'antd';
import { BookOutlined } from '@ant-design/icons';
import { fetchKbCollections } from '@/api/client';
import { useStore } from '@/store';

const { Text } = Typography;

export default function KbMountSwitch() {
  const { kbActiveMount, setKbActiveMount, kbCollections, setKbCollections } = useStore();
  const [options, setOptions] = useState<{ value: string; label: string }[]>([]);

  useEffect(() => {
    loadOptions();
  }, []);

  const loadOptions = async () => {
    try {
      const cols = await fetchKbCollections();
      setKbCollections(cols);
      setOptions(cols.filter((c) => c.status === 'ACTIVE').map((c) => ({ value: c.id, label: c.name })));
    } catch { /* silently fail */ }
  };

  const handleToggle = (checked: boolean) => {
    if (checked && !kbActiveMount.collectionId && options.length > 0) {
      setKbActiveMount({ mounted: true, collectionId: options[0].value, collectionName: options[0].label });
    } else if (checked) {
      setKbActiveMount({ mounted: true });
    } else {
      setKbActiveMount({ mounted: false });
    }
  };

  const handleSelect = (value: string) => {
    const col = kbCollections.find((c) => c.id === value);
    setKbActiveMount({ collectionId: value, collectionName: col?.name || '' });
  };

  return (
    <Space size={8}>
      <Tooltip title={kbActiveMount.mounted ? '知识库已挂载，点击关闭' : '挂载知识库到对话'}>
        <Switch
          checked={kbActiveMount.mounted}
          onChange={handleToggle}
          size="small"
          checkedChildren={<BookOutlined />}
          unCheckedChildren={<BookOutlined />}
        />
      </Tooltip>
      {kbActiveMount.mounted && (
        <Select
          value={kbActiveMount.collectionId}
          onChange={handleSelect}
          options={options}
          size="small"
          style={{ minWidth: 140 }}
          placeholder="选择知识库"
          onClick={() => { if (options.length === 0) loadOptions(); }}
          notFoundContent={<Text type="secondary" style={{ fontSize: 12 }}>暂无知识库</Text>}
        />
      )}
    </Space>
  );
}
