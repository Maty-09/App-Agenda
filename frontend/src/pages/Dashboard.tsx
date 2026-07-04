import React from 'react';
import { Calendar, CheckCircle, Clock, XCircle, LayoutDashboard, Settings, Users, Inbox } from 'lucide-react';

export default function Dashboard() {
  return (
    <div className="min-h-screen flex bg-slate-900 text-white">
      {/* Sidebar */}
      <aside className="w-64 glass-dark border-r border-slate-800 hidden md:flex flex-col">
        <div className="p-6">
          <h2 className="text-2xl font-bold tracking-tight text-white" style={{ fontFamily: 'Outfit' }}>NEXORA</h2>
          <p className="text-xs text-blue-400 mt-1 font-medium">B2B Edition</p>
        </div>
        <nav className="flex-1 px-4 space-y-2 mt-4">
          <a href="#" className="flex items-center px-4 py-3 bg-blue-600/20 text-blue-400 rounded-xl transition-all border border-blue-500/30">
            <LayoutDashboard className="w-5 h-5 mr-3" /> Dashboard
          </a>
          <a href="#" className="flex items-center px-4 py-3 text-slate-400 hover:bg-slate-800/50 hover:text-white rounded-xl transition-all">
            <Calendar className="w-5 h-5 mr-3" /> Agendas
          </a>
          <a href="#" className="flex items-center px-4 py-3 text-slate-400 hover:bg-slate-800/50 hover:text-white rounded-xl transition-all">
            <Users className="w-5 h-5 mr-3" /> Clientes
          </a>
          <a href="#" className="flex items-center px-4 py-3 text-slate-400 hover:bg-slate-800/50 hover:text-white rounded-xl transition-all">
            <Inbox className="w-5 h-5 mr-3" /> Tareas Kanban
          </a>
        </nav>
        <div className="p-4 mt-auto">
          <a href="#" className="flex items-center px-4 py-3 text-slate-400 hover:bg-slate-800/50 hover:text-white rounded-xl transition-all">
            <Settings className="w-5 h-5 mr-3" /> Configuración
          </a>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8 overflow-y-auto">
        <header className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold font-heading">Dashboard Ejecutivo</h1>
            <p className="text-slate-400 mt-1">Métricas en tiempo real de Nexora Default</p>
          </div>
          <div className="flex gap-4">
            <button className="px-4 py-2 bg-slate-800 border border-slate-700 rounded-xl text-sm font-medium hover:bg-slate-700 transition-all">Filtros: Este Mes</button>
            <button className="px-4 py-2 bg-blue-600 rounded-xl text-sm font-medium hover:bg-blue-500 transition-all flex items-center">
              + Nueva Agenda
            </button>
          </div>
        </header>

        {/* KPIs */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="glass-dark p-6 rounded-2xl border border-slate-800 relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-blue-500/10 rounded-bl-full blur-2xl group-hover:bg-blue-500/20 transition-all" />
            <div className="flex justify-between items-start mb-4 relative z-10">
              <h3 className="text-slate-400 font-medium">Agendas Hoy</h3>
              <Calendar className="w-6 h-6 text-blue-400" />
            </div>
            <p className="text-4xl font-bold text-white relative z-10">14</p>
            <p className="text-sm text-emerald-400 mt-2 relative z-10 flex items-center">↑ 12% vs ayer</p>
          </div>

          <div className="glass-dark p-6 rounded-2xl border border-slate-800 relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/10 rounded-bl-full blur-2xl group-hover:bg-emerald-500/20 transition-all" />
            <div className="flex justify-between items-start mb-4 relative z-10">
              <h3 className="text-slate-400 font-medium">Confirmadas</h3>
              <CheckCircle className="w-6 h-6 text-emerald-400" />
            </div>
            <p className="text-4xl font-bold text-white relative z-10">85</p>
            <p className="text-sm text-emerald-400 mt-2 relative z-10 flex items-center">↑ 5% mensual</p>
          </div>

          <div className="glass-dark p-6 rounded-2xl border border-slate-800 relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-amber-500/10 rounded-bl-full blur-2xl group-hover:bg-amber-500/20 transition-all" />
            <div className="flex justify-between items-start mb-4 relative z-10">
              <h3 className="text-slate-400 font-medium">Pendientes</h3>
              <Clock className="w-6 h-6 text-amber-400" />
            </div>
            <p className="text-4xl font-bold text-white relative z-10">12</p>
            <p className="text-sm text-slate-400 mt-2 relative z-10">Requieren acción</p>
          </div>

          <div className="glass-dark p-6 rounded-2xl border border-slate-800 relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-rose-500/10 rounded-bl-full blur-2xl group-hover:bg-rose-500/20 transition-all" />
            <div className="flex justify-between items-start mb-4 relative z-10">
              <h3 className="text-slate-400 font-medium">Canceladas</h3>
              <XCircle className="w-6 h-6 text-rose-400" />
            </div>
            <p className="text-4xl font-bold text-white relative z-10">3</p>
            <p className="text-sm text-emerald-400 mt-2 relative z-10 flex items-center">↓ 2% vs ayer</p>
          </div>
        </div>

        {/* Capacidad y Gráficos (Mockups estáticos por ahora) */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 glass-dark p-6 rounded-2xl border border-slate-800">
            <h3 className="text-lg font-bold mb-6">Utilización de Capacidad (Próximos 30 días)</h3>
            <div className="h-64 flex items-end justify-between gap-2">
              {/* Bars placeholder */}
              {[40, 70, 45, 90, 65, 30, 80, 50, 85, 60, 40, 75].map((h, i) => (
                <div key={i} className="w-full bg-slate-800 rounded-t-sm relative group">
                  <div 
                    className={`absolute bottom-0 w-full rounded-t-sm transition-all duration-500 ${h > 80 ? 'bg-rose-500' : 'bg-blue-500'}`} 
                    style={{ height: `${h}%` }}
                  />
                  {/* Tooltip hover */}
                  <div className="opacity-0 group-hover:opacity-100 absolute -top-8 left-1/2 -translate-x-1/2 bg-slate-700 text-xs px-2 py-1 rounded transition-opacity">
                    {h}%
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-between mt-4 text-xs text-slate-500 border-t border-slate-800 pt-4">
              <span>Hoy</span>
              <span>15 días</span>
              <span>30 días</span>
            </div>
          </div>

          <div className="glass-dark p-6 rounded-2xl border border-slate-800">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-bold">Tareas Urgentes</h3>
              <span className="bg-rose-500/20 text-rose-400 text-xs px-2 py-1 rounded-full font-medium">3 Críticas</span>
            </div>
            <div className="space-y-4">
              {[
                { title: "Contactar a Cliente VIP", desc: "Rechazó presupuesto", type: "Crítica" },
                { title: "Aprobar vacaciones técnico", desc: "Juan Pérez", type: "Media" },
                { title: "Revisar stock repuestos", desc: "Faltan frenos", type: "Alta" }
              ].map((task, i) => (
                <div key={i} className="p-4 bg-slate-800/50 rounded-xl border border-slate-700/50 hover:bg-slate-800 transition-colors cursor-pointer">
                  <div className="flex justify-between items-start mb-1">
                    <h4 className="font-medium text-sm text-slate-200">{task.title}</h4>
                    <span className={`text-[10px] uppercase font-bold tracking-wider ${task.type === 'Crítica' ? 'text-rose-400' : task.type === 'Alta' ? 'text-amber-400' : 'text-blue-400'}`}>
                      {task.type}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400">{task.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
