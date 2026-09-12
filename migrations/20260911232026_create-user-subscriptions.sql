-- Create user_subscriptions table
create table public.user_subscriptions (
    id uuid references auth.users(id) primary key,
    role text not null default 'student' check (role in ('student', 'admin')),
    fecha_inicio timestamptz default now(),
    fecha_fin timestamptz,
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- Enable RLS
alter table public.user_subscriptions enable row level security;

-- Policies for user_subscriptions
create policy "Users can view their own subscription"
    on public.user_subscriptions
    for select
    using (auth.uid() = id);

create policy "Admins can view all subscriptions"
    on public.user_subscriptions
    for select
    using (
        (select role from public.user_subscriptions where id = auth.uid()) = 'admin'
    );

create policy "Admins can update subscriptions"
    on public.user_subscriptions
    for update
    using (
        (select role from public.user_subscriptions where id = auth.uid()) = 'admin'
    );

create policy "Admins can insert subscriptions"
    on public.user_subscriptions
    for insert
    with check (
        (select role from public.user_subscriptions where id = auth.uid()) = 'admin'
    );

-- Trigger to automatically create a subscription profile for new users
create function public.handle_new_user()
returns trigger as $$
begin
  insert into public.user_subscriptions (id, role, fecha_inicio, fecha_fin)
  values (new.id, 'student', now(), now() + interval '7 days');
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();
