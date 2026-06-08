import { useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import { Result, Button, Descriptions, Card, message, Form, Input, Select, Skeleton, Tag } from 'antd';
import { useStore } from '@/store';
import { fetchProfile, updateProfile } from '@/api/client';

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

export default function ProfilePage() {
  const { onLoginRequired, isAuthenticated } = useOutletContext<OutletContext>();
  const { userId, userProfile, profileLoading, setProfile, setProfileLoading } = useStore();
  const [form] = Form.useForm();

  useEffect(() => {
    if (!isAuthenticated || !userId) return;
    setProfileLoading(true);
    fetchProfile(userId)
      .then((data) => { setProfile(data as Parameters<typeof setProfile>[0]); })
      .catch(() => { message.error('获取画像失败'); })
      .finally(() => { setProfileLoading(false); });
  }, [isAuthenticated, userId, setProfile, setProfileLoading]);

  const handleSave = async () => {
    const values = form.getFieldsValue();
    try {
      await updateProfile(userId, values);
      setProfile({ ...userProfile, ...values } as Parameters<typeof setProfile>[0]);
      message.success('画像已更新');
    } catch {
      message.error('更新失败');
    }
  };

  if (!isAuthenticated) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Result
          icon={<span style={{ fontSize: 48, opacity: 0.6 }}>👤</span>}
          title={<span className="cn-title" style={{ color: 'var(--ink)', letterSpacing: '0.05em' }}>需要登录</span>}
          subTitle={<span className="cn-tag">登录后查看和编辑画像</span>}
          extra={
            <Button type="primary" onClick={onLoginRequired}
              style={{ background: 'var(--ink)', border: 'none', boxShadow: '0 4px 12px rgba(42,37,32,0.15)', fontFamily: 'var(--font-sans)', letterSpacing: '0.08em' }}>
              登录
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div style={{ padding: 32, maxWidth: 720, margin: '0 auto' }}>
      <h2 className="cn-title" style={{ fontWeight: 600, color: 'var(--ink)', letterSpacing: '0.05em' }}>我的画像</h2>
      <div className="hand-line" style={{ margin: '12px 0 24px', maxWidth: 200 }} />

      {profileLoading ? (
        <Card style={{ background: 'rgba(255,255,255,0.6)', border: '1px solid var(--paper-dark)' }}>
          <Skeleton active paragraph={{ rows: 6 }} />
        </Card>
      ) : userProfile ? (
        <>
          <Card title={<span className="cn-sans" style={{ letterSpacing: '0.04em' }}>画像详情</span>}
            style={{ background: 'rgba(255,255,255,0.6)', border: '1px solid var(--paper-dark)', marginBottom: 24 }}>
            <Descriptions column={1} size="small"
              labelStyle={{ fontFamily: 'var(--font-sans)', color: 'var(--ink-soft)', width: 120 }}
              contentStyle={{ fontFamily: 'var(--font-serif)', color: 'var(--ink)' }}>
              <Descriptions.Item label="用户ID">{userProfile.user_id}</Descriptions.Item>
              <Descriptions.Item label="沟通风格">{userProfile.preferences.communication_style || '-'}</Descriptions.Item>
              <Descriptions.Item label="偏好深度">{userProfile.preferences.preferred_depth || '-'}</Descriptions.Item>
              <Descriptions.Item label="专长水平">{userProfile.expertise.level || '-'}</Descriptions.Item>
              <Descriptions.Item label="专长领域">
                {(userProfile.expertise.domains || []).map((d) => <Tag key={d} style={{ marginBottom: 4 }}>{d}</Tag>)}
              </Descriptions.Item>
              <Descriptions.Item label="技术栈">
                {(userProfile.expertise.tech_stack || []).map((t) => <Tag key={t} style={{ marginBottom: 4 }}>{t}</Tag>)}
              </Descriptions.Item>
              <Descriptions.Item label="常见任务类型">
                {(userProfile.habits.common_task_types || []).join(', ') || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="平均会话时长">
                {userProfile.habits.avg_session_duration_min
                  ? `${userProfile.habits.avg_session_duration_min} 分钟`
                  : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="最后更新">{userProfile.updated_at || '-'}</Descriptions.Item>
            </Descriptions>
          </Card>

          <Card title={<span className="cn-sans" style={{ letterSpacing: '0.04em' }}>编辑画像</span>}
            style={{ background: 'rgba(255,255,255,0.6)', border: '1px solid var(--paper-dark)' }}>
            <Form form={form} layout="vertical" initialValues={{
              communication_style: userProfile.preferences.communication_style || 'technical',
              preferred_depth: userProfile.preferences.preferred_depth || 'OVERVIEW',
              expertise_level: userProfile.expertise.level || 'intermediate',
              domains: (userProfile.expertise.domains || []).join(', '),
              tech_stack: (userProfile.expertise.tech_stack || []).join(', '),
            }}>
              <Form.Item name="communication_style" label={<span className="cn-tag">沟通风格</span>}>
                <Select options={[
                  { value: 'technical', label: '技术型' },
                  { value: 'business', label: '业务型' },
                  { value: 'casual', label: '随意' },
                ]} />
              </Form.Item>
              <Form.Item name="preferred_depth" label={<span className="cn-tag">偏好深度</span>}>
                <Select options={[
                  { value: 'OVERVIEW', label: '概览' },
                  { value: 'DETAILED', label: '详细' },
                  { value: 'DEEP_DIVE', label: '深度分析' },
                ]} />
              </Form.Item>
              <Form.Item name="expertise_level" label={<span className="cn-tag">专长水平</span>}>
                <Select options={[
                  { value: 'beginner', label: '初级' },
                  { value: 'intermediate', label: '中级' },
                  { value: 'advanced', label: '高级' },
                  { value: 'expert', label: '专家' },
                ]} />
              </Form.Item>
              <Form.Item name="domains" label={<span className="cn-tag">专长领域（逗号分隔）</span>}>
                <Input placeholder="例如: 后端架构, 分布式系统, 微服务" />
              </Form.Item>
              <Form.Item name="tech_stack" label={<span className="cn-tag">技术栈（逗号分隔）</span>}>
                <Input placeholder="例如: Java, Python, React, Docker" />
              </Form.Item>
              <Form.Item>
                <Button type="primary" onClick={handleSave}
                  style={{ background: 'var(--ink)', border: 'none', fontFamily: 'var(--font-sans)', letterSpacing: '0.04em' }}>
                  保存
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </>
      ) : (
        <Card style={{ background: 'rgba(255,255,255,0.6)', border: '1px solid var(--paper-dark)', textAlign: 'center', padding: 40 }}>
          <p className="cn-tag">暂无画像数据</p>
          <p className="cn-tag" style={{ fontSize: 13, color: 'var(--ink-faint)' }}>完成首次对话后，系统将自动分析并生成你的画像</p>
        </Card>
      )}
    </div>
  );
}
