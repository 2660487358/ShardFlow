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
      width: '100%',
    }}>
      <ChatPanel onLoginRequired={onLoginRequired} isAuthenticated={isAuthenticated} />
    </div>
  );
}
