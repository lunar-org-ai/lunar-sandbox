import { Activity, Command, Download, Home, List, Play } from "lucide-react";
import { Link, useLocation } from "react-router";

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
} from "@/components/ui/sidebar";
import { Badge } from "@/components/ui/badge";

const navItems = [
  { title: "Home", url: "/", icon: Home },
  { title: "New Run", url: "/launcher", icon: Play },
  { title: "Runs", url: "/runs", icon: List },
  { title: "Pool", url: "/pool", icon: Activity },
  { title: "Export", url: "/export", icon: Download },
];

export function AppSidebar() {
  const location = useLocation();

  return (
    <Sidebar
      collapsible="icon"
      className="group-data-[variant=sidebar]:border-0"
    >
      <SidebarHeader>
        <div className="flex items-center gap-2 px-2 py-2">
          <div className="size-6 rounded-lg bg-foreground flex items-center justify-center shrink-0">
            <span className="text-xs font-bold text-background">L</span>
          </div>
          <span className="font-semibold text-sm truncate">LunarEngine</span>
          <Badge variant="secondary" className="text-xs ml-auto">
            Live
          </Badge>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="text-xs uppercase tracking-wide">
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
        <div className="px-2 pb-2 space-y-1 group-data-[collapsible=icon]:hidden">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <kbd className="inline-flex items-center gap-0.5 rounded bg-secondary px-1.5 py-0.5 font-mono text-xs text-secondary-foreground">
              <Command className="size-2.5" />K
            </kbd>
            <span>Open command menu</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <kbd className="inline-flex items-center rounded bg-secondary px-1.5 py-0.5 font-mono text-xs text-secondary-foreground">
              ?
            </kbd>
            <span>View shortcuts</span>
          </div>
        </div>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}
