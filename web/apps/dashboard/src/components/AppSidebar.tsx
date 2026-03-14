import { Activity, Download, Home, List, Play } from 'lucide-react'
import { Link, useLocation } from 'react-router'

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'

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

      <SidebarRail />
    </Sidebar>
  )
}
