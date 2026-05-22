import { useOutletContext } from 'react-router-dom';
import ChatPanel from '@/components/chat/ChatPanel';

interface OutletContext {
  onLoginRequired: () => void;
  isAuthenticated: boolean;
}

export default function ChatPage() {
  const { onLoginRequired, isAuthenticated } = useOutletContext<OutletContext>();

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      maxWidth: 720,
      margin: '0 auto',
      width: '100%',
      padding: '0 24px',
    }}>
      <ChatPanel onLoginRequired={onLoginRequired} isAuthenticated={isAuthenticated} />
    </div>
  );
}
