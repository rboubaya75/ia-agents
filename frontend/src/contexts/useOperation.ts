import { useContext } from 'react';
import OperationContext, { type OperationContextType } from './OperationContext';

export const useOperation = (): OperationContextType => {
  const context = useContext(OperationContext);
  if (!context) {
    throw new Error('useOperation doit être utilisé dans un OperationProvider');
  }
  return context;
};
