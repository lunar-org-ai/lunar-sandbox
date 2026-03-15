import { Activity, Command, Download, Home, List, Play } from 'lucide-react'
import { Link, useLocation } from 'react-router'

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'
import { Separator } from '@/components/ui/separator'

const navItems = [
  { title: 'Home', url: '/', icon: Home },
  { title: 'New Run', url: '/launcher', icon: Play },
  { title: 'Runs', url: '/runs', icon: List },
  { title: 'Pool', url: '/pool', icon: Activity },
  { title: 'Export', url: '/export', icon: Download },
]

export function AppSidebar() {
  const location = useLocation()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center gap-2.5 px-2 py-1.5">
          <div className="size-6 rounded-lg bg-foreground flex items-center justify-center shrink-0">
            <span className="text-xs font-bold text-background">L</span>
          </div>
          <span className="font-semibold text-sm tracking-tight text-foreground truncate">LunarEngine</span>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="text-[11px] font-medium text-muted-foreground/60 uppercase tracking-wider">
            Navigation
          </SidebarGroupLabel>
          <SidebarMenu>
            {navItems.map((item) => (
              <SidebarMenuItem key={item.url}>
                <SidebarMenuButton
                  asChild
                  isActive={location.pathname === item.url}
                  tooltip={item.title}
                >
                  <Link to={item.url}>
                    <item.icon className="size-4" />
                    <span>{item.title}</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <Separator className="mb-2" />
        <div className="px-2 pb-2 space-y-1 group-data-[collapsible=icon]:hidden">
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground/50">
            <kbd className="inline-flex items-center gap-0.5 rounded border border-border/50 bg-muted px-1 py-0.5 font-mono text-[10px]">
              <Command className="size-2.5" />K
            </kbd>
            <span>Search</span>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground/50">
            <kbd className="inline-flex items-center rounded border border-border/50 bg-muted px-1 py-0.5 font-mono text-[10px]">
              ?
            </kbd>
            <span>Shortcuts</span>
          </div>
        </div>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  )
}
