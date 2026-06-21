import { useEffect, useState, useRef } from 'react';
import { useOutletContext, useParams, useNavigate } from 'react-router-dom';
import ChatPanel from '@/components/chat/ChatPanel';
import SessionExpiredModal from '@/components/chat/SessionExpiredModal';
import { useStore } from '@/store';
import {
  initSession,
  fetchSessionMessages,
  fetchSessionExpiry,
  type SessionMessageItem,
} from '@/api/client';
import type { ChatMessage } from '@/types';

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

// Session 过期检查间隔（5 分钟）
const EXPIRY_CHECK_INTERVAL_MS = 5 * 60 * 1000;
// 预创建防抖：避免短时间内重复调用
const INIT_DEBOUNCE_MS = 2000;

export default function ChatPage() {
  const { onLoginRequired, isAuthenticated } = useOutletContext<OutletContext>();
  // T1.4: 读取 URL 参数 sessionId，支持 /chat/:sessionId 路由续接
  const { sessionId: urlSessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();
  const {
    setActiveTask,
    activeSessionId,
    activeTaskId,
    clearMessages,
    addMessage,
    clearActiveTask,
  } = useStore();

  const [expiryModal, setExpiryModal] = useState<{
    open: boolean;
    mode: 'expired' | 'expiring_soon';
    remainingSeconds?: number;
  }>({ open: false, mode: 'expired' });

  const lastInitRef = useRef<number>(0);
  const initingRef = useRef<boolean>(false);
  const expiryNotifiedRef = useRef<string>(''); // 避免重复弹窗

  // T2.3: 预创建 Session —— 进入 Chat 页且无有效 session 时调用 /sessions/init
  useEffect(() => {
    if (!isAuthenticated) return;
    // URL 中已有 sessionId 时不预创建（走历史恢复路径）
    if (urlSessionId) return;
    // 已有 activeSessionId 时不预创建
    if (activeSessionId) return;

    const now = Date.now();
    if (now - lastInitRef.current < INIT_DEBOUNCE_MS) return;
    if (initingRef.current) return;

    initingRef.current = true;
    lastInitRef.current = now;

    initSession({ source_port: 'web' })
      .then((result) => {
        setActiveTask(result.task_id, result.session_id);
        // URL rewrite: /chat -> /chat/{sessionId}
        navigate(`/chat/${result.session_id}`, { replace: true });
      })
      .catch((err: unknown) => {
        // T2.2: 预创建失败时降级为首条消息由 /conversation 兜底创建
        console.warn('[Session] Pre-create failed, will fallback to /conversation:', err);
      })
      .finally(() => {
        initingRef.current = false;
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, urlSessionId, activeSessionId]);

  // T2.5: 历史消息恢复 —— URL 进入或刷新时拉取历史消息
  useEffect(() => {
    if (!isAuthenticated) return;
    if (!urlSessionId) {
      // 无 URL sessionId 时清空消息（新建对话场景）
      if (!activeSessionId) clearMessages();
      return;
    }

    // URL sessionId 与当前 store 一致且消息已加载时跳过
    if (urlSessionId === activeSessionId) return;

    let cancelled = false;
    fetchSessionMessages(urlSessionId, { limit: 50 })
      .then((result) => {
        if (cancelled) return;
        clearMessages();
        setActiveTask(activeTaskId || urlSessionId, urlSessionId);
        // 按时间顺序渲染历史消息
        const historicalMessages: ChatMessage[] = result.messages.map(
          (m: SessionMessageItem) => ({
            id: m.msg_id || `${m.timestamp}_${m.role}`,
            role: (m.role === 'user' ? 'user' : m.role === 'assistant' ? 'assistant' : 'system') as 'user' | 'assistant' | 'system',
            content: m.content,
            timestamp: new Date(m.timestamp).getTime() || Date.now(),
          }),
        );
        historicalMessages.forEach((msg) => addMessage(msg));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const status = (err as { response?: { status?: number } })?.response?.status;
        // 401/403/404 错误给出明确用户提示
        if (status === 401) {
          onLoginRequired();
        } else if (status === 403) {
          clearActiveTask();
          clearMessages();
          import('antd').then(({ message }) => {
            message.error('无权访问该会话');
          });
          navigate('/chat', { replace: true });
        } else if (status === 404) {
          // 会话已过期或不存在，清空并预创建新会话
          clearActiveTask();
          clearMessages();
          navigate('/chat', { replace: true });
        } else {
          console.warn('[Session] Failed to load history:', err);
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlSessionId, isAuthenticated]);

  // T2.6: Session 过期检查 —— 定时拉取过期状态，展示过期/即将过期提示
  useEffect(() => {
    if (!isAuthenticated || !activeSessionId) return;

    let cancelled = false;

    const checkExpiry = async () => {
      if (cancelled || !activeSessionId) return;
      try {
        const status = await fetchSessionExpiry(activeSessionId);
        if (cancelled) return;

        if (status.expired) {
          // 过期提示仅一次
          if (expiryNotifiedRef.current !== `${activeSessionId}:expired`) {
            expiryNotifiedRef.current = `${activeSessionId}:expired`;
            setExpiryModal({ open: true, mode: 'expired' });
          }
        } else if (status.expiring_soon) {
          // 即将过期提示仅一次
          if (expiryNotifiedRef.current !== `${activeSessionId}:expiring`) {
            expiryNotifiedRef.current = `${activeSessionId}:expiring`;
            setExpiryModal({
              open: true,
              mode: 'expiring_soon',
              remainingSeconds: status.remaining_seconds,
            });
          }
        } else {
          // 会话正常时重置通知状态
          expiryNotifiedRef.current = '';
        }
      } catch (err) {
        // 过期检查失败时静默降级，不阻断主流程
        console.debug('[Session] Expiry check failed:', err);
      }
    };

    // 首次延迟 10 秒检查，避免与预创建/历史加载竞争
    const initialTimer = setTimeout(checkExpiry, 10_000);
    const interval = setInterval(checkExpiry, EXPIRY_CHECK_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearTimeout(initialTimer);
      clearInterval(interval);
    };
  }, [isAuthenticated, activeSessionId]);

  const handleNewSession = () => {
    clearActiveTask();
    clearMessages();
    expiryNotifiedRef.current = '';
    setExpiryModal({ open: false, mode: 'expired' });
    navigate('/chat', { replace: true });
    // 触发预创建
    setTimeout(() => {
      if (!isAuthenticated) return;
      initSession({ source_port: 'web' })
        .then((result) => {
          setActiveTask(result.task_id, result.session_id);
          navigate(`/chat/${result.session_id}`, { replace: true });
        })
        .catch(() => {
          // 降级：由 /conversation 兜底
        });
    }, 100);
  };

  const handleCloseExpiryModal = () => {
    setExpiryModal((prev) => ({ ...prev, open: false }));
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      width: '100%',
    }}>
      <ChatPanel onLoginRequired={onLoginRequired} isAuthenticated={isAuthenticated} />
      <SessionExpiredModal
        open={expiryModal.open}
        mode={expiryModal.mode}
        remainingSeconds={expiryModal.remainingSeconds}
        onNewSession={handleNewSession}
        onClose={handleCloseExpiryModal}
      />
    </div>
  );
}
