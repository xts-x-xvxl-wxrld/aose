import React from 'react'
import { useUIStore } from '@/stores/uiStore'
import ChatWindow from '@/workspace/chat/ChatWindow'
import ObjectViewer from '@/workspace/ObjectViewer'

export default function MainWindow() {
  const mainMode = useUIStore((s) => s.mainMode)

  if (mainMode === 'chat') return <ChatWindow />
  return <ObjectViewer />
}
