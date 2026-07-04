import React, { useState, useEffect } from 'react';
import { LayoutDashboard, Settings, Users, Inbox, Calendar, Plus, MoreVertical } from 'lucide-react';

interface Task {
  id: number;
  titulo: str;
  descripcion: string;
  estado: string;
  prioridad: string;
}

const KANBAN_COLUMNS = ['Pendiente', 'En progreso', 'En revisión', 'Completada'];

export default function Kanban() {
  const [tasks, setTasks] = useState<Task[]>([
    { id: 1, titulo: "Contactar Cliente", descripcion: "Llamar por presupuesto", estado: "Pendiente", prioridad: "Alta" },
    { id: 2, titulo: "Revisión Sistema", descripcion: "Chequeo de frenos", estado: "En progreso", prioridad: "Crítica" },
    { id: 3, titulo: "Facturar mensualidad", descripcion: "Empresa XYZ", estado: "Completada", prioridad: "Media" },
  ]);

  const handleDragStart = (e: React.DragEvent, taskId: number) => {
    e.dataTransfer.setData("taskId", taskId.toString());
  };

  const handleDrop = (e: React.DragEvent, newEstado: string) => {
    const taskId = parseInt(e.dataTransfer.getData("taskId"));
    setTasks(tasks.map(t => t.id === taskId ? { ...t, estado: newEstado } : t));
    // TODO: Llamar a la API de FastAPI (PUT /api/v1/tareas/{id})
  };

  const allowDrop = (e: React.DragEvent) => {
    e.preventDefault();
  };

  return (
    <div className="min-h-screen flex bg-slate-900 text-white">
      {/* Sidebar (Simplificado) */}
      <aside className="w-64 glass-dark border-r border-slate-800 hidden md:flex flex-col">
        <div className="p-6">
          <h2 className="text-2xl font-bold tracking-tight text-white" style={{ fontFamily: 'Outfit' }}>NEXORA</h2>
        </div>
        <nav className="flex-1 px-4 space-y-2 mt-4">
          <a href="/dashboard" className="flex items-center px-4 py-3 text-slate-400 hover:bg-slate-800/50 rounded-xl transition-all">
            <LayoutDashboard className="w-5 h-5 mr-3" /> Dashboard
          </a>
          <a href="#" className="flex items-center px-4 py-3 bg-blue-600/20 text-blue-400 rounded-xl transition-all border border-blue-500/30">
            <Inbox className="w-5 h-5 mr-3" /> Tareas Kanban
          </a>
        </nav>
      </aside>

      {/* Main Kanban Content */}
      <main className="flex-1 p-8 overflow-x-hidden">
        <header className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold font-heading">Tablero de Tareas</h1>
            <p className="text-slate-400 mt-1">Gestión operativa de tu equipo</p>
          </div>
          <button className="px-4 py-2 bg-blue-600 rounded-xl text-sm font-medium hover:bg-blue-500 transition-all flex items-center">
            <Plus className="w-4 h-4 mr-2" /> Nueva Tarea
          </button>
        </header>

        <div className="flex gap-6 overflow-x-auto pb-8 h-[calc(100vh-160px)]">
          {KANBAN_COLUMNS.map(col => (
            <div 
              key={col} 
              className="flex-shrink-0 w-80 flex flex-col bg-slate-800/30 rounded-2xl border border-slate-700/50 p-4"
              onDragOver={allowDrop}
              onDrop={(e) => handleDrop(e, col)}
            >
              <div className="flex justify-between items-center mb-4 px-2">
                <h3 className="font-semibold text-slate-200">{col}</h3>
                <span className="bg-slate-700 text-xs px-2 py-1 rounded-full text-slate-300">
                  {tasks.filter(t => t.estado === col).length}
                </span>
              </div>
              
              <div className="flex-1 overflow-y-auto space-y-3 pr-2 custom-scrollbar">
                {tasks.filter(t => t.estado === col).map(task => (
                  <div
                    key={task.id}
                    draggable
                    onDragStart={(e) => handleDragStart(e, task.id)}
                    className="glass p-4 rounded-xl cursor-grab active:cursor-grabbing hover:border-slate-500 transition-colors group"
                  >
                    <div className="flex justify-between items-start mb-2">
                      <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full ${
                        task.prioridad === 'Crítica' ? 'bg-rose-500/20 text-rose-400' : 
                        task.prioridad === 'Alta' ? 'bg-amber-500/20 text-amber-400' : 
                        'bg-blue-500/20 text-blue-400'
                      }`}>
                        {task.prioridad}
                      </span>
                      <MoreVertical className="w-4 h-4 text-slate-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                    <h4 className="text-sm font-medium text-slate-100 mb-1">{task.titulo}</h4>
                    <p className="text-xs text-slate-400 line-clamp-2">{task.descripcion}</p>
                    
                    <div className="mt-4 flex items-center justify-between text-slate-500 text-xs">
                      <div className="flex items-center gap-1">
                        <div className="w-6 h-6 rounded-full bg-slate-700 border border-slate-600 flex justify-center items-center">
                          <span className="text-[10px] text-white">OP</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        <span>Hoy</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
